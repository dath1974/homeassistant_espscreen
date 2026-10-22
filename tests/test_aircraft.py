"""Aircraft over a map tile (docs/MAP.md, "Aircraft"): a sensor that lists flights, as Flightradar24's Current in area
does, read by the add-on and sent to the screen as pixels on the map's picture (op "air"), again on every report."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import aircraft  # noqa: E402
import map_card  # noqa: E402
from core import extras, screen_options, validate_layout  # noqa: E402

SOURCE = 'sensor.flightradar24_current_in_area'


def flight(id='abc', lat=52.0, lon=5.0, altitude=35000, heading=90, speed=450, callsign='KLM123', **more):
    return {'id': id, 'latitude': lat, 'longitude': lon, 'altitude': altitude, 'heading': heading, 'ground_speed': speed,
            'callsign': callsign, 'aircraft_code': 'B738', 'airport_origin_code_iata': 'AMS',
            'airport_destination_code_iata': 'LHR', 'on_ground': 0, **more}


def state(*flights):
    return {'state': str(len(flights)), 'attributes': {'friendly_name': 'Current in area', 'flights': list(flights)}}


def tile(**options):
    return {'entity': 'screen.map', 'options': {'display': 'map', 'aircraft': SOURCE, **options}}


VIEW = map_card.View(52.0, 5.0, 10.0, (400, 300))


class ReadingTest(unittest.TestCase):
    def test_flightradar24_fields(self):
        f = aircraft.flights_of(state(flight()))[0]
        self.assertEqual((f.id, f.lat, f.lon, f.altitude, f.heading, f.speed, f.callsign, f.model, f.origin, f.destination),
                         ('abc', 52.0, 5.0, 35000, 90, 450, 'KLM123', 'B738', 'AMS', 'LHR'))
        self.assertFalse(f.on_ground)

    def test_without_a_place_or_twice_is_left_out(self):
        listed = state(flight(lat=None), flight(id='x', lat=95), flight(id='a'), flight(id='a'), 'nonsense')
        self.assertEqual([f.id for f in aircraft.flights_of(listed)], ['a'])

    def test_no_list_no_flights(self):
        self.assertEqual(aircraft.flights_of({'attributes': {'flights': 'none'}}), [])
        self.assertEqual(aircraft.flights_of(None), [])

    def test_sources_are_sensors_that_list_flights(self):
        states = {SOURCE: state(), 'sensor.other': {'state': '1', 'attributes': {}},
                  'binary_sensor.x': {'state': 'on', 'attributes': {'flights': []}}}
        self.assertEqual([s['id'] for s in aircraft.sources(states)], [SOURCE])


class ChoosingTest(unittest.TestCase):
    def options(self, **chosen):
        return aircraft.options_of(tile(**chosen))

    def test_altitudes_and_ground(self):
        flights = aircraft.flights_of(state(flight('low', altitude=2000), flight('high', altitude=38000),
                                            flight('parked', altitude=0, on_ground=1)))
        self.assertEqual([f.id for f in aircraft.shown(flights, self.options(), VIEW)], ['low', 'high'])
        self.assertEqual([f.id for f in aircraft.shown(flights, self.options(plane_min=10000), VIEW)], ['high'])
        self.assertEqual(sorted(f.id for f in aircraft.shown(flights, self.options(plane_ground='show'), VIEW)), ['high', 'low', 'parked'])

    def test_closest_first_and_at_most(self):
        flights = aircraft.flights_of(state(flight('far', lon=5.2), flight('near', lon=5.01), flight('mid', lon=5.1)))
        self.assertEqual([f.id for f in aircraft.shown(flights, self.options(plane_most=2), VIEW)], ['near', 'mid'])

    def test_outside_the_frame(self):
        flights = aircraft.flights_of(state(flight('gone', lat=53.5)))
        self.assertEqual(aircraft.shown(flights, self.options(), VIEW), [])


class LabelTest(unittest.TestCase):
    def test_each_kind(self):
        f = aircraft.flights_of(state(flight()))[0]
        self.assertEqual(aircraft.label_of(f, 'none', False), '')
        self.assertEqual(aircraft.label_of(f, 'callsign', False), 'KLM123')
        self.assertEqual(aircraft.label_of(f, 'altitude', False), 'KLM123\n35000 ft')
        self.assertEqual(aircraft.label_of(f, 'full', False), 'KLM123 · B738\n35000 ft · 450 kn\nAMS – LHR')
        self.assertEqual(aircraft.label_of(f, 'altitude', True), 'KLM123\n10670 m')

    def test_auto_follows_the_room(self):
        options = aircraft.options_of(tile())
        self.assertEqual(aircraft.label_kind(options, (120, 120), 1.0, False), 'none')
        self.assertEqual(aircraft.label_kind(options, (200, 200), 1.0, False), 'callsign')
        self.assertEqual(aircraft.label_kind(options, (400, 300), 1.0, False), 'altitude')
        self.assertEqual(aircraft.label_kind(options, (120, 120), 1.0, True), 'altitude')


class OverlayTest(unittest.TestCase):
    def test_a_plane_on_the_frame(self):
        flights = aircraft.flights_of(state(flight()))
        [plane] = aircraft.overlay(VIEW, flights, aircraft.options_of(tile()))
        x, y, heading, band, vx, vy, label, track, watched = plane
        self.assertEqual((x, y, heading, band, track), (200, 150, 90, 4, []))
        # 450 knots due east at zoom 10 over 52 degrees north: about 151 pixels a minute.
        self.assertTrue(140 < vx < 160 and vy == 0, (vx, vy))
        self.assertEqual(label, 'KLM123\n35000 ft')

    def test_hold_sends_no_motion(self):
        [plane] = aircraft.overlay(VIEW, aircraft.flights_of(state(flight())), aircraft.options_of(tile(plane_motion='hold')))
        self.assertEqual(plane[4:6], [0, 0])

    def test_track_is_the_last_seconds(self):
        tracks = aircraft.Tracks()
        for moment, lon in ((0, 4.9), (30, 4.95), (60, 5.0)):
            tracks.update(SOURCE, aircraft.flights_of(state(flight(lon=lon))), moment)
        options = aircraft.options_of(tile(plane_track='show', plane_track_s=40))
        [plane] = aircraft.overlay(VIEW, aircraft.flights_of(state(flight())), options, tracks, SOURCE, now=60)
        track = plane[7]
        self.assertEqual(len(track), 4)
        self.assertEqual(track[-2:], [200, 150])
        self.assertLess(track[0], 200)

    def test_a_plane_gone_is_forgotten(self):
        tracks = aircraft.Tracks()
        tracks.update(SOURCE, aircraft.flights_of(state(flight())), 0)
        tracks.update(SOURCE, [], aircraft.FORGET_SECONDS + 1)
        self.assertEqual(tracks.of(SOURCE, 'abc', 900, aircraft.FORGET_SECONDS + 1), [])

    def test_message_fits_the_screen(self):
        planes = [[100 + n, 100, 90, 3, 50, 0, 'CALLSIGN' + str(n) + '\n35000 ft · 450 kn\nAMS – LHR', list(range(40))] for n in range(20)]
        body = aircraft.message('tile', 3, (400, 300), planes, {'m': 'dot', 'c': 'altitude', 'g': 1})
        self.assertLessEqual(len(json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode()), aircraft.MESSAGE_BYTES)
        self.assertGreater(len(body['a']), 5)
        self.assertEqual((body['op'], body['t'], body['i'], body['w'], body['h']), ('air', 'tile', 3, 400, 300))

    def test_the_cards_a_screen_asks_for(self):
        self.assertEqual(aircraft.cards_of({'air': 'tile', 'cards': '3:180x120,5:400x300,3:1x1,x:2x2,7:9000x10'}, 800),
                         [(3, (180, 120)), (5, (400, 300))])
        self.assertEqual(aircraft.cards_of({'air': 'full', 'idx': '4', 'size': '800x480'}, 800), [(4, (800, 480))])
        self.assertEqual(aircraft.cards_of({'air': 'full', 'idx': '4', 'size': '0x480'}, 800), [])


class WatchTest(unittest.TestCase):
    """Watched aircraft: a registration or callsign with a colour each, shown whatever the rest of the choices say."""
    WATCH = [{'id': 'G-EZAB', 'colour': 'red'}, {'id': 'BAW432', 'colour': 'blue'}]

    def options(self, **chosen):
        return aircraft.options_of(tile(plane_watch=self.WATCH, **chosen))

    def test_matched_by_registration_or_callsign(self):
        by_registration = aircraft.flights_of(state(flight('a', callsign='EZY1', aircraft_registration='GEZAB')))[0]
        by_callsign = aircraft.flights_of(state(flight('b', callsign='BAW432')))[0]
        nobody = aircraft.flights_of(state(flight('c', callsign='KLM1')))[0]
        watched = self.options()['plane_watch']
        self.assertEqual([aircraft.watch_colour(f, watched) for f in (by_registration, by_callsign, nobody)],
                         [1, aircraft.WATCH_COLOURS.index('blue') + 1, 0])

    def test_shown_beyond_altitude_ground_and_most_and_last(self):
        flights = aircraft.flights_of(state(flight('near', lon=5.01), flight('mid', lon=5.05),
                                            flight('low', altitude=500, callsign='BAW432', lon=5.1),
                                            flight('parked', altitude=0, on_ground=1, callsign='X', aircraft_registration='G-EZAB')))
        shown = aircraft.shown(flights, self.options(plane_most=1, plane_min=10000), VIEW)
        self.assertEqual([f.id for f in shown], ['near', 'low', 'parked'])
        # Still not off the frame: there is nowhere to draw it.
        far = aircraft.flights_of(state(flight('far', lat=53.5, callsign='BAW432')))
        self.assertEqual(aircraft.shown(far, self.options(), VIEW), [])

    def test_always_labelled_with_its_colour(self):
        flights = aircraft.flights_of(state(flight('a', callsign='KLM1'), flight('b', callsign='BAW432', lon=5.02)))
        planes = aircraft.overlay(VIEW, flights, self.options(plane_label='none'))
        self.assertEqual([(p[6], p[8]) for p in planes], [('', 0), ('BAW432', aircraft.WATCH_COLOURS.index('blue') + 1)])

    def test_kept_when_the_message_is_too_long(self):
        planes = [[100 + n, 100, 90, 3, 50, 0, 'CALLSIGN' + str(n) + '\n35000 ft · 450 kn\n' + 'A' * 160, list(range(40)), 0] for n in range(20)]
        planes.append([5, 5, 90, 3, 0, 0, 'BAW432', [], 4])
        body = aircraft.message('tile', 0, (400, 300), planes, {'m': 'dot', 'c': 'altitude', 'g': 1})
        self.assertEqual(body['a'][-1][6], 'BAW432')
        self.assertLess(len(body['a']), 21)

    def test_saved_in_capitals_once_each(self):
        saved = validate_layout({'title': 'x', 'tiles': [{'entity': 'screen.map', 'options': {'display': 'map', 'plane_watch': [
            {'id': 'g-ezab', 'colour': 'red'}, {'id': 'GEZAB', 'colour': 'blue'}, {'id': 'BAW432', 'colour': 'green'}]}}]})['tiles'][0]
        self.assertEqual(saved['options']['plane_watch'], [{'id': 'G-EZAB', 'colour': 'red'}, {'id': 'BAW432', 'colour': 'green'}])
        for wrong in ([{'id': 'X', 'colour': 'red'}], [{'id': 'BAW432', 'colour': 'pink'}], [{'id': 'BAW432'}], 'BAW432',
                      [{'id': f'AB{n}', 'colour': 'red'} for n in range(aircraft.WATCH_MOST + 1)]):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                validate_layout({'title': 'x', 'tiles': [{'entity': 'screen.map', 'options': {'display': 'map', 'plane_watch': wrong}}]})


class ShowTest(unittest.TestCase):
    """What the map tile shows: its people and aircraft, its people only or its aircraft only."""

    def test_people_only_asks_for_no_planes(self):
        self.assertEqual(aircraft.source_of(tile(show='people')), '')
        self.assertEqual(aircraft.source_of(tile(show='aircraft')), SOURCE)
        self.assertNotIn('air', extras(tile(show='people'), {}))

    def test_aircraft_only_has_nobody_and_no_zones(self):
        self.assertEqual(map_card.shown(tile(show='aircraft', follow='chosen', map=['person.sam'])), [])
        self.assertFalse(map_card.people_shown(tile(show='aircraft')))
        self.assertTrue(map_card.people_shown({'entity': 'person.me', 'options': {'display': 'map', 'show': 'aircraft'}}))

    def test_a_place_of_its_own(self):
        view = map_card.frame_view('place', 'town', [], [], (400, 300), centre=(51.47, -0.4543))
        self.assertEqual((view.lat, view.lon), (51.47, -0.4543))
        home = SimpleNamespace(home=True, lat=52.0, lon=5.0, radius=100)
        view = map_card.frame_view('place', 'town', [], [home], (400, 300))
        self.assertEqual((view.lat, view.lon), (52.0, 5.0), 'home while it has no place')
        # Everyone with nobody to fit is around home too.
        self.assertEqual((map_card.frame_view('everyone', 'town', [], [home], (400, 300)).lat), 52.0)

    def test_saved(self):
        def save(entity='screen.map', **options):
            return validate_layout({'title': 'x', 'tiles': [{'entity': entity, 'options': {'display': 'map', **options}}]})['tiles'][0]['options']
        self.assertEqual(save(show='both', framing='place', centre=[51.4700012, -0.454321]),
                         {'display': 'map', 'framing': 'place', 'centre': [51.47, -0.45432]})
        self.assertEqual(save(show='aircraft'), {'display': 'map', 'show': 'aircraft'})
        self.assertEqual(save('person.me', show='aircraft', framing='place', centre=[1, 2]),
                         {'display': 'map', 'framing': 'place', 'centre': [1.0, 2.0]})
        for wrong in ({'show': 'planes'}, {'centre': [91, 0]}, {'centre': [1]}, {'centre': 'here'}, {'centre': [True, 1]}):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                save(**wrong)


class RadiusTest(unittest.TestCase):
    """The distance `radius`: a circle of metres round the middle, a little smaller than the frame's short side."""

    def test_the_circle_spans_the_short_side_with_room(self):
        for size in ((400, 300), (300, 600)):
            view = map_card.frame_view('place', 'radius', [], [], size, centre=(52.0, 5.0), radius=20000)
            across = 2 * 20000 / map_card.metres_per_pixel(52.0, view.zoom)
            self.assertAlmostEqual(across * map_card.RADIUS_ROOM, min(size), delta=0.5)

    def test_planes_outside_it_are_left_out_but_not_watched_ones(self):
        tile_options = aircraft.options_of(tile(plane_watch=[{'id': 'BAW432', 'colour': 'red'}]))
        view = map_card.View(52.0, 5.0, 9.0, (400, 300))
        flights = aircraft.flights_of(state(flight('in', lon=5.05), flight('out', lon=5.4),
                                            flight('watched', lon=5.4, lat=52.01, callsign='BAW432')))
        circle = (52.0, 5.0, 10000)
        self.assertEqual([f.id for f in aircraft.shown(flights, tile_options, view, circle)], ['in', 'watched'])
        self.assertEqual(sorted(f.id for f in aircraft.shown(flights, tile_options, view)), ['in', 'out', 'watched'])

    def test_the_circle_of_a_tile(self):
        board = map_card.Board({'dpi': 170})
        placed = {'entity': 'screen.map', 'options': {'display': 'map', 'framing': 'place', 'centre': [51.47, -0.45],
                                                      'distance': 'radius', 'radius': 30000}}
        self.assertEqual(map_card.circle_of(placed, {}, (400, 300), board), (51.47, -0.45, 30000))
        self.assertIsNone(map_card.circle_of({**placed, 'options': {**placed['options'], 'distance': 'town'}}, {}, (400, 300), board))
        everyone = {**placed, 'options': {**placed['options'], 'framing': 'everyone'}}
        self.assertIsNone(map_card.circle_of(everyone, {}, (400, 300), board))

    def test_shaded_inside_with_an_edge(self):
        board = map_card.Board({'dpi': 170})
        placed = {'entity': 'screen.map', 'options': {'display': 'map', 'framing': 'place', 'centre': [52.0, 5.0],
                                                      'distance': 'radius', 'radius': 5000, 'overlay': 'none', 'show': 'aircraft'}}
        for dark in (False, True):
            image = map_card.render_tile(placed, {}, (400, 300), board, dark)
            inside, outside = image.getpixel((200, 150)), image.getpixel((5, 5))
            # A shade darker in the light look, so white streets keep their contrast, and lighter in the dark one.
            if dark:
                self.assertGreater(sum(inside), sum(outside))
            else:
                self.assertLess(sum(inside), sum(outside))
            # The edge, 1/1.1 of half the short side from the middle, stands apart from both.
            edge = image.getpixel((200, round(150 - 150 / map_card.RADIUS_ROOM)))
            self.assertNotEqual(edge, inside)

    def test_saved_in_metres_without_the_default(self):
        def save(**options):
            return validate_layout({'title': 'x', 'tiles': [{'entity': 'screen.map', 'options': {'display': 'map', **options}}]})['tiles'][0]['options']
        self.assertEqual(save(framing='home', distance='radius', radius=25000), {'display': 'map', 'framing': 'home', 'distance': 'radius', 'radius': 25000})
        self.assertEqual(save(distance='radius', radius=map_card.RADIUS[0]), {'display': 'map', 'distance': 'radius'})
        for wrong in (100, 600000, 2.5, True, '10'):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                save(radius=wrong)


class TapTest(unittest.TestCase):
    def test_the_map_tile_opens_bare_or_not_at_all(self):
        def save(tap):
            return validate_layout({'title': 'x', 'tiles': [{'entity': 'screen.map', 'options': {'display': 'map', 'tap': tap}}]})['tiles'][0]['options']
        self.assertEqual(save('clean'), {'display': 'map', 'tap': 'clean'})
        self.assertEqual(save('none'), {'display': 'map', 'tap': 'none'})
        # The screen gets the tap, which its firmware reads (runtime_tiles.h: camera_open bare).
        self.assertEqual(screen_options({'entity': 'screen.map', 'options': {'display': 'map', 'tap': 'clean'}}, {})['tap'], 'clean')
        firmware = (ROOT / 'components/smart_display/runtime_tiles.h').read_text()
        self.assertIn('camera_open(card.entity, card.name, (int)w.index, "", card.tap == "clean")', firmware)


class LayoutTest(unittest.TestCase):
    def save(self, entity='screen.map', **options):
        return validate_layout({'title': 'x', 'tiles': [{'entity': entity, 'options': {'display': 'map', **options}}]})['tiles'][0]

    def test_the_map_tile_keeps_its_choices_without_defaults(self):
        saved = self.save(aircraft=SOURCE, plane_marker='dot', plane_track='show', plane_track_s=120, plane_most=15)
        self.assertEqual(saved['options'], {'display': 'map', 'aircraft': SOURCE, 'plane_track': 'show', 'plane_track_s': 120})

    def test_wrong_choices_are_refused(self):
        for wrong in ({'plane_most': 21}, {'plane_marker': 'jet'}, {'aircraft': 'person.me'}, {'plane_min': 20000, 'plane_max': 10000},
                      {'plane_track_s': True}):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                self.save(**wrong)

    def test_a_persons_map_has_no_aircraft(self):
        self.assertEqual(self.save('person.me', aircraft=SOURCE, plane_marker='plane')['options'], {'display': 'map'})

    def test_the_screen_gets_a_flag_and_no_choice(self):
        saved = self.save(aircraft=SOURCE, plane_marker='plane')
        self.assertEqual(screen_options(saved, {}), {'display': 'map'})
        self.assertEqual(extras(saved, {})['air'], 1)
        self.assertNotIn('air', extras(self.save(), {}))


class HelloTest(unittest.TestCase):
    def test_the_firmware_says_it_draws_aircraft(self):
        # The app answers only a screen whose hello names aircraft.FEATURE; a board that draws pictures says so.
        core_yaml = (ROOT / 'packages/core.yaml').read_text()
        self.assertIn(f'if (runtime_tiles::camera_supported()) features.add("{aircraft.FEATURE}");', core_yaml)


class PickedTest(unittest.TestCase):
    """A plane picked on a full view (`air:<id>`): its id on the full view's planes, and its card."""
    WORDS = {'ground': 'On the ground', 'squawk': 'Squawk'}

    def test_a_full_views_planes_carry_their_id(self):
        options = aircraft.options_of(tile())
        [card] = aircraft.overlay(VIEW, aircraft.flights_of(state(flight())), options)
        [full] = aircraft.overlay(VIEW, aircraft.flights_of(state(flight())), options, full=True)
        self.assertEqual(len(card), 9, 'a card on the page has no use for it')
        self.assertEqual(full[9], 'abc')
        self.assertEqual(aircraft.picked_of('air:abc'), 'abc')
        for focus in ('', 'person.sam', 'air:', None, 'air:' + 'x' * 33):
            self.assertIsNone(aircraft.picked_of(focus), focus)

    def test_the_card_of_a_plane(self):
        item = flight(airline='KLM Royal Dutch Airlines', flight_number='KL1601', aircraft_model='Embraer E190',
                      aircraft_registration='PH-EZA', airport_origin_city='Billund', airport_destination_city='London',
                      altitude=2500, speed=160, vertical_speed=-800, squawk='4521')
        self.assertIs(aircraft.item_of(state(flight('other'), item), 'abc'), item)
        self.assertIsNone(aircraft.item_of(state(item), 'gone'))
        card = aircraft.card(item, False, self.WORDS)
        glyph = aircraft.tile_icons.GLYPHS
        self.assertEqual(card['t'], 'KLM123')
        self.assertEqual(card['r'], [
            [glyph['airplane'], 'KLM Royal Dutch Airlines', 'KL1601'],
            [glyph['map-marker'], 'Billund – London', 'AMS – LHR'],
            [glyph['information-outline'], 'Embraer E190', 'PH-EZA'],
            [glyph['arrow-down'], '2500 ft', '160 kn'],
            [glyph['information-outline'], 'Squawk', '4521']])
        # Metric where Home Assistant counts in kilometres; level flight, on the ground; only what the source gives.
        metric = aircraft.card(flight(vertical_speed=50), True, self.WORDS)
        self.assertEqual(metric['r'][-1], [glyph['arrow-right'], '10670 m', '833 km/h'])
        self.assertEqual(aircraft.card(flight(vertical_speed=900), False, self.WORDS)['r'][-1][0], glyph['arrow-up'])
        ground = aircraft.card(flight(on_ground=1, speed=12), False, self.WORDS)
        self.assertEqual(ground['r'][-1], [glyph['speedometer'], 'On the ground', '12 kn'])
        bare = aircraft.card({'id': 'x1', 'latitude': 1, 'longitude': 2, 'aircraft_registration': 'N12345'}, False, self.WORDS)
        self.assertEqual(bare, {'t': 'N12345', 'r': [[glyph['information-outline'], '', 'N12345']]})
        self.assertIsNone(aircraft.card({'id': 'x1'}, False, self.WORDS), 'no place, no plane')


class ScreenTest(unittest.IsolatedAsyncioTestCase):
    """A screen that asks for the planes of its map cards gets them as op "air", and again on every report."""

    async def test_asked_answered_and_followed(self):
        from manager_fixtures import with_screen_grid, seed_layout
        from test_camera import fake_ha
        from test_map_card import STATES
        from server import Manager
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha()
            ha.states.update(STATES)
            ha.states['sensor.d1_fw']['state'] = '0.21.0'
            # Over the home zone of STATES, and one far away.
            ha.states[SOURCE] = state(flight('near', lat=52.3587, lon=4.8682), flight('far', lat=10.0, lon=10.0))
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Home', 'tiles': [
                {'entity': 'screen.map', 'name': '', 'options': {'size': 'wide', 'framing': 'home', 'aircraft': SOURCE,
                                                                 'plane_track': 'show'}},
                {'entity': 'person.sam', 'name': ''}]}))

            def sent():
                out = [entry[2] for entry in ha.log if entry[0] == 'send' and entry[2].get('op') == 'air']
                ha.log.clear()
                return out
            ask = {'inbox': 'text.d1_tiles', 'air': 'tile', 'cards': '0:448x118,1:200x118'}
            # A screen whose firmware draws no aircraft is sent none.
            await m.answer_camera(ask)
            self.assertEqual(sent(), [])
            m.page_senders['text.d1_tiles'] = SimpleNamespace(features={'aircraft'}, protocol=None, session=None, confirmed=None)
            await m.answer_camera(ask)
            [message] = sent()
            self.assertEqual((message['t'], message['i'], message['w'], message['h']), ('tile', 0, 448, 118))
            [plane] = message['a']
            self.assertEqual(plane[:2], [224, 59], 'the plane over home stands in the middle of a map around home')
            # A report of the sensor moves it on every card that asked, with its track behind it.
            ha.states[SOURCE] = state(flight('near', lat=52.3587, lon=4.8700))
            m.ha.states[SOURCE] = ha.states[SOURCE]
            await m.air_reports({SOURCE})
            [message] = sent()
            self.assertGreater(message['a'][0][0], 224)
            # Another sensor's report sends nothing; nor does a card the screen stopped asking for.
            await m.air_reports({'sensor.other'})
            self.assertEqual(sent(), [])
            for card in m.air_cards.values():
                card['until'] = 0
            await m.air_reports({SOURCE})
            self.assertEqual(sent(), [])
            # The full view: its tile, its picture's size, its focus and move come back with the planes.
            await m.answer_camera({'inbox': 'text.d1_tiles', 'air': 'full', 'idx': '0', 'size': '400x300', 'move': '1,0.00,0.00', 'focus': ''})
            [message] = sent()
            self.assertEqual((message['t'], message['w'], message['mv'], message['f']), ('full', 400, '1,0.00,0.00', ''))
            # A plane picked on the full view: its card comes with the planes, and again with every report.
            ha.states[SOURCE] = state(flight('near', lat=52.3587, lon=4.8700, airline='KLM', flight_number='KL123'))
            m.ha.states[SOURCE] = ha.states[SOURCE]
            await m.answer_camera({'inbox': 'text.d1_tiles', 'air': 'full', 'idx': '0', 'size': '400x300', 'move': '', 'focus': 'air:near'})
            [message] = sent()
            self.assertEqual(message['f'], '', 'a plane picked is the same view as nobody picked')
            self.assertEqual(message['a'][0][9], 'near')
            self.assertEqual((message['m']['f'], message['m']['c']['t']), ('air:near', 'KLM123'))
            self.assertEqual(message['m']['c']['r'][0][1:], ['KLM', 'KL123'])
            ha.states[SOURCE] = state(flight('other', lat=52.3587, lon=4.8700))
            m.ha.states[SOURCE] = ha.states[SOURCE]
            await m.air_reports({SOURCE})
            [message] = sent()
            self.assertEqual(message['m'], {'f': 'air:near'}, 'gone from the source: its card goes')
            # A tile that is no map with aircraft is never answered.
            await m.answer_camera({'inbox': 'text.d1_tiles', 'air': 'full', 'idx': '1', 'size': '400x300'})
            self.assertEqual(sent(), [])
            # The sensor is watched, so its reports reach the sync loop.
            self.assertIn(SOURCE, m.watched_entities())


if __name__ == '__main__':
    unittest.main()
