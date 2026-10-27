"""A map drawn as a radar scope (docs/MAP.md, "Radar"): the scope in its phosphor whatever the look, the same phosphors
in the add-on and the firmware, and the aircraft over it told to take the scope's style."""
import importlib.util
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import aircraft  # noqa: E402
import catalogue  # noqa: E402
import map_card  # noqa: E402
from core import MAP_OPTIONS, validate_layout  # noqa: E402

HAS_PIL = importlib.util.find_spec('PIL') is not None
JFK = [40.6413, -73.7781]


def tile(**options):
    return {'entity': 'screen.map', 'name': 'Scope', 'options': {'display': 'map', 'show': 'aircraft', 'framing': 'place',
                                                                'centre': JFK, 'streets': 'radar', **options}}


def save(**options):
    layout = {'title': 'x', 'tiles': [{'entity': 'screen.map', 'options': {'display': 'map', **options}}]}
    return validate_layout(layout)['tiles'][0]['options']


class Choices(unittest.TestCase):
    def test_a_base_map_and_its_phosphors(self):
        map_options = catalogue.of_type('person')['map']
        self.assertEqual(map_options['streets'][-1], 'radar')
        self.assertEqual(tuple(map_options['scope']), tuple(map_card.SCOPE), 'the catalogue names the phosphors in their order')
        self.assertEqual(MAP_OPTIONS['scope'], map_card.CHOICES['scope'])
        self.assertEqual(catalogue.of_type('person')['map']['aircraft']['plane_sweep'], ['hide', 'show'])

    def test_saved_without_defaults(self):
        self.assertEqual(save(streets='radar', scope='amber', plane_sweep='show')['scope'], 'amber')
        options = save(streets='radar', scope='green', plane_sweep='hide')
        self.assertNotIn('scope', options)
        self.assertNotIn('plane_sweep', options)
        with self.assertRaises(ValueError):
            save(streets='radar', scope='purple')

    def test_a_scope_is_no_chart_and_draws_on_the_streets(self):
        self.assertIsNone(map_card.chart_of(tile()))
        self.assertTrue(map_card.wants_streets(tile()), 'its coast, water and highways come from the street tiles')
        self.assertEqual(map_card.scope_of(tile(scope='blue')), 'blue')
        self.assertEqual(map_card.scope_of(tile()), 'green')
        self.assertIsNone(map_card.scope_of(tile(streets='show', scope='blue')))


class SameAsTheFirmware(unittest.TestCase):
    def test_the_phosphors_are_theme_h_radar_tints(self):
        theme = (ROOT / 'components/smart_display/theme.h').read_text()
        block = re.search(r'namespace radar \{.*?TINTS\[\] = \{(.*?)\};', theme, re.S)[1]
        tints = [tuple(int(n, 16) for n in found) for found in re.findall(r'\{(0x\w+), (0x\w+), (0x\w+)\}', block)]
        self.assertEqual(tints, list(map_card.SCOPE.values()))

    def test_the_screen_reads_the_phosphors_by_their_names(self):
        receiver = (ROOT / 'components/smart_display/page_receiver.cpp').read_text()
        names = re.search(r'TINTS\[theme::radar::TINT_COUNT\] = \{(.*?)\};', receiver)[1]
        self.assertEqual(re.findall(r'"(\w+)"', names), list(map_card.SCOPE))


class Rings(unittest.TestCase):
    def test_at_most_four_rings_to_the_nearer_edge(self):
        self.assertEqual(map_card.ring_step(100, 150), 0.5)    # 100 px a mile, 150 to the edge: rings every half mile
        self.assertEqual(map_card.ring_step(10, 150), 5)
        self.assertEqual(map_card.ring_step(0.01, 150), map_card.RING_STEPS[-1])
        for px, near in ((3.3, 200), (40, 90), (1, 400)):
            self.assertLessEqual(near / (map_card.ring_step(px, near) * px), map_card.RINGS)

    def test_miles_written_short(self):
        self.assertEqual([map_card._miles(n) for n in (0.25, 0.5, 1, 2.5, 10)], ['.25', '.5', '1', '2.5', '10'])


@unittest.skipUnless(HAS_PIL, 'Pillow')
class Drawing(unittest.TestCase):
    board = map_card.Board({'dpi': 170})

    def test_its_phosphor_whatever_the_look(self):
        light = map_card.render_tile(tile(scope='amber', overlay='none', distance='region'), {}, (300, 200), self.board, False)
        dark = map_card.render_tile(tile(scope='amber', overlay='none', distance='region'), {}, (300, 200), self.board, True)
        self.assertEqual(light.tobytes(), dark.tobytes())
        ground = map_card._rgb(map_card.SCOPE['amber'][0])
        corner = light.getpixel((2, 3))
        self.assertTrue(all(abs(a - b) <= 6 for a, b in zip(corner, ground)), corner)
        r, g, b = light.getpixel((150, 100))
        self.assertTrue(r > 150 and g > 120 and b < g, ('a hot cross on the middle', (r, g, b)))

    def test_dark_beyond_the_distance_circle(self):
        board, size = self.board, (300, 300)
        inside = tile(overlay='none', distance='radius', radius=20000)
        image = map_card.render_tile(inside, {}, size, board)
        middle = map_card.scope_middle(inside, {}, size, board)
        self.assertEqual((round(middle[0]), round(middle[1])), (150, 150))
        ground = map_card._rgb(map_card.SCOPE['green'][0])
        # The corners lie outside the circle: the ground; the glow inside is a little lighter.
        self.assertTrue(all(abs(a - b) <= 4 for a, b in zip(image.getpixel((4, 4)), ground)), image.getpixel((4, 4)))
        self.assertGreater(image.getpixel((150, 120))[1], image.getpixel((4, 4))[1])

    def test_moved_by_the_keys_the_scope_stands_round_the_new_middle(self):
        board, size = self.board, (400, 300)
        moved = map_card.scope_middle(tile(distance='region'), {}, size, board, full=True, move=(1, 50.0, -20.0))
        self.assertEqual(moved[:2], (200.0, 150.0), 'the middle of the view the keys show')
        # The distance's circle keeps its metres round that middle: a step out draws it half as large, and the rose with
        # it; a step closer it outgrows the glass, and the rose stays on the largest circle the glass holds.
        circled = tile(distance='radius', radius=10000)
        _, _, rose = map_card.scope_middle(circled, {}, size, board, full=True)
        _, _, further = map_card.scope_middle(circled, {}, size, board, full=True, move=(-1, 0.0, 0.0))
        _, _, closer = map_card.scope_middle(circled, {}, size, board, full=True, move=(1, 0.0, 0.0))
        self.assertAlmostEqual(further, rose / 2, delta=1.0)
        self.assertAlmostEqual(closer, 150 - 4, delta=0.5)
        # And the planes are kept round it: the circle the app cuts them at is the one drawn.
        lat, lon, metres = map_card.circle_of(circled, {}, size, board, None, (0, 120.0, 0.0))
        view = map_card.moved(map_card.view_for(circled, {}, size, board, full=True), (0, 120.0, 0.0))
        self.assertEqual(metres, 10000)
        x, y = view.point(lat, lon)
        self.assertAlmostEqual(x, 200.0, delta=0.5)
        self.assertAlmostEqual(y, 150.0, delta=0.5)
        # A map of streets keeps its circle round the middle it was framed on, wherever the keys moved it.
        streets = {**circled, 'options': {**circled['options'], 'streets': 'show'}}
        self.assertEqual(map_card.circle_of(streets, {}, size, board, None, (0, 120.0, 0.0)), map_card.circle_of(streets, {}, size, board))
        self.assertIsNone(map_card.scope_middle(tile(streets='show'), {}, size, board))

    def test_the_rose_is_the_circle_the_beam_turns_in(self):
        board, size = self.board, (400, 300)
        x, y, rose = map_card.scope_middle(tile(distance='region'), {}, size, board)
        self.assertAlmostEqual(rose, min(x, 400 - x, y, 300 - y) - 4, places=3, msg='the largest circle the frame holds')
        _, _, circled = map_card.scope_middle(tile(distance='radius', radius=20000), {}, size, board)
        self.assertLess(circled, 150, 'the distance radius circle, a little inside the short side')
        self.assertGreater(circled, 120)


class Planes(unittest.TestCase):
    def test_the_style_names_the_scope(self):
        options = aircraft.options_of(tile(plane_sweep='show'))
        self.assertNotIn('r', aircraft.style_of(options))
        style = aircraft.style_of(options, ('amber', (120.4, 80.6, 99.6)))
        self.assertEqual(style['r'], {'t': 'amber', 'x': 120, 'y': 81, 'e': 100, 'w': 0}, 'a card on the page never sweeps')
        self.assertEqual(aircraft.style_of(options, ('amber', (120, 80, 50)), full=True)['r']['w'], 1)
        hidden = aircraft.options_of(tile())
        self.assertEqual(aircraft.style_of(hidden, ('green', (0, 0, 0)), full=True)['r']['w'], 0)

    def test_a_scope_sends_motion_for_its_vectors_even_when_planes_hold(self):
        flights = aircraft.flights_of({'attributes': {'flights': [
            {'id': 'a', 'callsign': 'KLM1', 'latitude': 52.0, 'longitude': 5.0, 'altitude': 30000, 'heading': 90, 'ground_speed': 450}]}})
        view = map_card.View(52.0, 5.0, 10.0, (300, 200))
        options = aircraft.options_of({'options': {'plane_motion': 'hold'}})
        [held] = aircraft.overlay(view, flights, options)
        [scope] = aircraft.overlay(view, flights, options, radar=True)
        self.assertEqual(held[4:6], [0, 0])
        self.assertGreater(scope[4], 0, 'heading east: to the right a minute on')
        self.assertEqual(aircraft.style_of(options, ('green', (0, 0, 0)))['g'], 0, 'and still the screen holds them')


if __name__ == '__main__':
    unittest.main()
