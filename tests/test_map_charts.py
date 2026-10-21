"""Charts under a map card (docs/MAP.md, "Charts"): the FAA's and the USGS's picture tiles in place of the streets,
from their own servers, at the zooms each is printed for, with the streets wherever a chart has nothing."""
from manager_fixtures import with_screen_grid, seed_layout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import camera_feed  # noqa: E402
import catalogue  # noqa: E402
import map_card  # noqa: E402
import map_charts  # noqa: E402
from core import MAP_OPTIONS, validate_layout  # noqa: E402

HAS_PIL = importlib.util.find_spec('PIL') is not None
HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
RED = (220, 30, 30)
# Chicago, well inside every chart.
CHICAGO = [41.9786, -87.9048]


def sheet(colour=RED):
    from PIL import Image
    out = io.BytesIO()
    Image.new('RGB', (256, 256), colour).save(out, 'JPEG')
    return out.getvalue()


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Choices(unittest.TestCase):
    def test_every_chart_is_a_choice_of_the_catalogue(self):
        streets = catalogue.of_type('person')['map']['streets']
        self.assertEqual(streets[:2], ['show', 'hide'], 'the streets stay the default, a plain ground the next')
        self.assertEqual(set(streets[2:]), set(map_charts.CHARTS))
        self.assertEqual(tuple(streets), map_card.CHOICES['streets'], MAP_OPTIONS['streets'])
        for chart, about in map_charts.CHARTS.items():
            self.assertTrue(about['night'] == 'invert' or 0 < about['night'] < 1, chart)

    def test_a_chart_is_kept_with_the_tile_and_an_unknown_one_is_refused(self):
        tile = validate_layout({'title': 'x', 'tiles': [{'entity': 'screen.map', 'options': {'display': 'map', 'streets': 'sectional'}}]})['tiles'][0]
        self.assertEqual(tile['options']['streets'], 'sectional')
        self.assertEqual(map_card.chart_of(tile), 'sectional')
        self.assertTrue(map_card.wants_streets(tile), 'the streets where the chart has nothing')
        with self.assertRaises(ValueError):
            validate_layout({'title': 'x', 'tiles': [{'entity': 'screen.map', 'options': {'display': 'map', 'streets': 'satellite'}}]})
        for streets in ('show', 'hide'):
            self.assertIsNone(map_card.chart_of({'entity': 'screen.map', 'options': {'streets': streets}}))


class Zooms(unittest.TestCase):
    def test_a_chart_shows_at_the_zooms_it_is_printed_for(self):
        self.assertEqual(map_charts.chart_zoom('sectional', 10.5), 11, 'region')
        self.assertEqual(map_charts.chart_zoom('sectional', 12.0), 11, 'a little magnified past its sharpest zoom')
        self.assertIsNone(map_charts.chart_zoom('sectional', 13.0), 'town: closer than it is printed for, the streets')
        self.assertEqual(map_charts.chart_zoom('sectional', 6.0), 8, 'before its first zoom: its first, made smaller')
        self.assertEqual(map_charts.chart_zoom('ifr_high', 10.5), 9)
        self.assertIsNone(map_charts.chart_zoom('ifr_high', 11.0))
        self.assertEqual(map_charts.chart_zoom('topo', 16.5), 16, 'street')
        for chart in map_charts.CHARTS:
            self.assertIsNotNone(map_charts.chart_zoom(chart, map_card.DISTANCES['region']), chart)
        # A glass twice as dense draws a tile twice as large, so its text keeps its size.
        self.assertEqual(map_charts.chart_zoom('sectional', 13.0, 2.0), 11)
        self.assertEqual(map_charts.chart_zoom('sectional', 10.5, 2.0), 10)
        self.assertIsNone(map_charts.chart_zoom('sectional', 13.5, 2.0))

    def test_the_tiles_under_a_view(self):
        view = map_card.View(*CHICAGO, 11.0, (480, 320))
        keys = map_charts.keys_for(view, 'sectional')
        self.assertTrue(keys and all(z == 11 for z, _, _ in keys))
        self.assertEqual(len(keys), len(view.tiles()), 'the same squares as the streets at a whole zoom')
        self.assertEqual(map_charts.keys_for(map_card.View(*CHICAGO, 13.0, (480, 320)), 'sectional'), [])
        self.assertEqual(map_charts.keys_for(view, 'satellite'), [])
        # Far before a chart's first zoom it would take too many tiles: the streets.
        self.assertEqual(map_charts.keys_for(map_card.View(*CHICAGO, 4.0, (800, 480)), 'sectional'), [])


class Source(unittest.IsolatedAsyncioTestCase):
    async def test_tiles_are_asked_once_and_kept(self):
        asked = []

        async def fetch(url):
            asked.append(url)
            return b'' if url.endswith('/2') else b'tile'
        source = map_charts.ChartSource(fetch, Clock())
        first = await source.tiles('sectional', [(11, 1, 1), (11, 2, 2)])
        self.assertEqual(first, {(11, 1, 1): b'tile', (11, 2, 2): b''})
        self.assertEqual(asked[0], map_charts.FAA + '/VFR_Sectional/MapServer/tile/11/1/1', 'z, then y, then x')
        await source.tiles('sectional', [(11, 1, 1)])
        self.assertEqual(len(asked), 2, 'kept, the empty square too')
        self.assertTrue(map_charts.drawable(first))
        self.assertFalse(map_charts.drawable({(11, 2, 2): b''}))
        # A zoom the chart does not draw is never asked for.
        self.assertEqual(await source.tiles('sectional', [(14, 1, 1)]), {(14, 1, 1): b''})
        self.assertEqual(len(asked), 2)

    async def test_a_server_that_gives_nothing_is_left_alone_for_a_while(self):
        asked, clock = [], Clock()

        async def fetch(url):
            asked.append(url)
            raise ConnectionError('down')
        source = map_charts.ChartSource(fetch, clock)
        with self.assertLogs('map_charts', 'INFO'):
            self.assertEqual(await source.tiles('topo', [(10, 1, 1)]), {})
        self.assertFalse(source.available('topo'))
        self.assertTrue(source.available('sectional'), 'each chart its own server')
        self.assertEqual(await source.tiles('topo', [(10, 1, 1)]), {})
        self.assertEqual(len(asked), 1)
        clock.now += map_charts.COOLDOWN
        self.assertTrue(source.available('topo'))


@unittest.skipUnless(HAS_PIL, 'Pillow')
class Drawing(unittest.TestCase):
    TILE = {'entity': 'screen.map', 'options': {'display': 'map', 'show': 'aircraft', 'framing': 'place', 'centre': CHICAGO,
                                                'distance': 'region', 'overlay': 'none', 'streets': 'sectional'}}

    def chart_for(self, size, board, colour=RED):
        view = map_card.view_for(self.TILE, {}, size, board)
        return {key: sheet(colour) for key in map_charts.keys_for(view, 'sectional', board.scale)}

    def test_the_chart_is_drawn_in_place_of_the_streets(self):
        board, size = map_card.Board({'dpi': 170}), (400, 300)
        image = map_card.render_tile(self.TILE, {}, size, board, False, None, chart=self.chart_for(size, board))
        self.assertTrue(all(abs(a - b) < 20 for a, b in zip(image.getpixel((200, 150)), RED)), image.getpixel((200, 150)))

    def test_in_the_dark_look_the_sectional_is_darkened(self):
        board, size = map_card.Board({'dpi': 170}), (400, 300)
        dark = map_card.render_tile(self.TILE, {}, size, board, True, None, chart=self.chart_for(size, board, (250, 230, 40))).getpixel((200, 150))
        night = map_charts.CHARTS['sectional']['night']
        self.assertTrue(all(abs(a - round(b * night)) < 12 for a, b in zip(dark, (250, 230, 40))), dark)

    def test_in_the_dark_look_an_inverted_chart_turns_its_light_round_and_keeps_its_hue(self):
        board, size = map_card.Board({'dpi': 170}), (400, 300)
        tile = {**self.TILE, 'options': {**self.TILE['options'], 'streets': 'topo'}}
        self.assertEqual(map_charts.CHARTS['topo']['night'], 'invert')

        def dark(colour):
            view = map_card.view_for(tile, {}, size, board)
            chart = {key: sheet(colour) for key in map_charts.keys_for(view, 'topo', board.scale)}
            return map_card.render_tile(tile, {}, size, board, True, None, chart=chart).getpixel((200, 150))
        ground, ink = map_card._rgb(map_card.DARK['land']), map_card._rgb(map_card.DARK['ink'])
        self.assertTrue(all(abs(a - b) < 6 for a, b in zip(dark((255, 255, 255)), ground)), 'white paper: the dark ground')
        self.assertTrue(all(abs(a - b) < 6 for a, b in zip(dark((0, 0, 0)), ink)), 'black ink: the dark look\'s ink')
        r, g, b = dark((250, 230, 40))
        self.assertTrue(r > b + 25 and g > b + 25, ('yellow stays yellowish, a dark olive', (r, g, b)))
        r, g, b = dark((20, 90, 160))
        self.assertGreater(b, r + 40, ('blue stays bluish', (r, g, b)))

    def test_without_a_chart_tile_the_ground_is_plain(self):
        board, size = map_card.Board({'dpi': 170}), (400, 300)
        empty = {key: b'' for key in self.chart_for(size, board)}
        image = map_card.render_tile(self.TILE, {}, size, board, False, {}, chart=empty)
        self.assertEqual(image.getpixel((200, 150)), map_card._rgb(map_card.LIGHT['land']))


@unittest.skipUnless(HAS_PIL and HAS_AIOHTTP, 'Pillow and aiohttp')
class Screens(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        camera_feed.base_url.__defaults__[0].clear()

    async def ask(self, chart_tile):
        from test_camera import fake_ha, picture
        from test_map_card import STATES, TILE
        from server import Manager
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (900, 600)))
            ha.states.update(STATES)
            ha.states['sensor.d1_fw']['state'] = '0.21.0'

            async def map_tile(z, x, y):
                ha.log.append(('tile', (z, x, y)))
                return TILE

            async def chart(url):
                ha.log.append(('chart', url))
                return chart_tile
            ha.map_tile, ha.chart_tile = map_tile, chart
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            layout = validate_layout({'title': 'Home', 'tiles': [{'entity': 'screen.map', 'name': '', 'options': {
                'display': 'map', 'show': 'aircraft', 'framing': 'place', 'centre': CHICAGO, 'distance': 'region', 'streets': 'sectional'}}]})
            seed_layout(m, 'text.d1_tiles', layout)
            with self.assertLogs('screen_manager', 'INFO'):
                await m.answer_camera({'inbox': 'text.d1_tiles', 'tiles': 'screen.map', 'idx': '0', 'size': '54', 'bg': 'E7E7E7',
                                       'atlas': json.dumps([[0, 0, 218, 118, 14, 0]]), 'dark': '0'})
            sent = [entry[2] for entry in ha.log if entry[0] == 'send']
            status, raw, _ = await m.camera.serve(sent[0]['u'].rsplit('/', 1)[1][:-4])
            with Image.open(io.BytesIO(raw)) as image:
                return [entry[0] for entry in ha.log], image.convert('RGB')

    async def test_a_screen_gets_the_chart_and_no_streets(self):
        asked, image = await self.ask(sheet())
        self.assertIn('chart', asked)
        self.assertNotIn('tile', asked, 'the chart is drawn: no streets are asked for')
        self.assertTrue(all(abs(a - b) < 30 for a, b in zip(image.getpixel((100, 60)), RED)), image.getpixel((100, 60)))

    async def test_outside_the_chart_the_screen_gets_the_streets(self):
        asked, _ = await self.ask(b'')
        self.assertIn('chart', asked)
        self.assertIn('tile', asked)


class Fetching(unittest.IsolatedAsyncioTestCase):
    async def test_only_a_charts_own_server_is_asked_without_home_assistants_key(self):
        from server import HomeAssistant

        class Session:
            calls, status = [], 200

            def get(self, url, headers=None, timeout=None, allow_redirects=True):
                Session.calls.append((url, headers, allow_redirects))
                outer = self

                class Response:
                    status = outer.status

                    class content:
                        @staticmethod
                        async def iter_chunked(size):
                            yield b'tile'

                    def raise_for_status(self):
                        pass

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *error):
                        return False
                return Response()
        session = Session()
        ha = HomeAssistant(session, 'http://ha/api', 'token')
        url = map_charts.CHARTS['topo']['url'].format(z=10, x=1, y=2)
        self.assertEqual(await ha.chart_tile(url), b'tile')
        sent, headers, redirects = Session.calls[-1]
        self.assertEqual((sent, redirects), (url, False))
        self.assertNotIn('Authorization', headers)
        self.assertIn('ESP Screen Manager', headers['User-Agent'])
        Session.status = 404
        self.assertEqual(await ha.chart_tile(url), b'', 'a square the chart has nothing in')
        for wrong in ('http://ha/api/states', 'https://example.com/tile/1/1/1'):
            with self.assertRaises(ValueError):
                await ha.chart_tile(wrong)


if __name__ == '__main__':
    unittest.main()
