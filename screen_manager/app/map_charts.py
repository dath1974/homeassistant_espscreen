"""Charts under a map card instead of its streets: the FAA's aeronautical charts and the USGS topographic map.

A map's `streets` can name a chart (CHARTS) in place of OpenStreetMap's streets. Unlike the streets these are pictures,
256-pixel tiles in the same Web Mercator squares, and Home Assistant has no proxy for them: the add-on asks the chart's
own server, which is public and needs no key. A request names a zoom and two whole numbers, as one through Home Assistant
does, and carries the app's name. Both are United States government services and cover the United States: a square
without a chart (outside its coverage, or a zoom it does not draw) is answered with nothing, and a card with no chart
under it is drawn with its streets.

A chart is printed for a scale, and its service draws closer levels than it was scanned at, magnified. So each chart
has the tile zooms worth asking for (`zoom`: its service's first, and the closest still sharp) and the closest view it
is drawn at (`most`), past which the card shows its streets. A card draws the chart at the tile zoom nearest its own
(dpi-corrected: a dense glass draws a tile larger rather than its text smaller).
"""
import asyncio
from collections import OrderedDict
import logging
import math
import time

LOG = logging.getLogger(__name__)

FAA = 'https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services'
# key -> the tile address ({z}/{y}/{x}, as ArcGIS orders them), the tile zooms worth asking for, the closest view it is
# drawn at, and what the card credits. The sectional is scanned at about zoom 10 and the IFR charts at 8 (high) and 10
# (low); one level closer is still sharp enough. The region distance (10.5) shows every chart.
CHARTS = {
    'sectional': {'url': FAA + '/VFR_Sectional/MapServer/tile/{z}/{y}/{x}', 'zoom': (8, 11), 'most': 12.0, 'credit': 'FAA'},
    'ifr_low': {'url': FAA + '/IFR_AreaLow/MapServer/tile/{z}/{y}/{x}', 'zoom': (7, 11), 'most': 12.0, 'credit': 'FAA'},
    'ifr_high': {'url': FAA + '/IFR_High/MapServer/tile/{z}/{y}/{x}', 'zoom': (5, 9), 'most': 10.5, 'credit': 'FAA'},
    'topo': {'url': 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}',
             'zoom': (0, 16), 'most': 17.5, 'credit': 'USGS'},
}
TILE_PX = 256
# The most tiles one card asks for: a view far before a chart's first zoom would need many more.
MOST_TILES = 48
# The charts follow a 56-day cycle and the topographic map changes more slowly: a day is fresh enough.
TILE_TTL = 24 * 60 * 60
CACHE_BYTES = 32 * 1024 * 1024
MAX_TILE_BYTES = 1024 * 1024
FETCH_SECONDS = 15
MAX_CONCURRENT = 4
COOLDOWN = 600


def chart_zoom(chart, zoom, dpi_scale=1.0):
    """The tile zoom a view at `zoom` draws `chart` at, or None when the chart has nothing readable for it."""
    low, high = CHARTS[chart]['zoom']
    # A tile is drawn at its own pixels on a 170 dpi glass; a denser one draws it larger, so its text stays readable.
    wanted = zoom - math.log2(max(1.0, dpi_scale))
    if wanted > CHARTS[chart]['most'] + 1e-9:
        return None
    return max(low, min(high, int(math.floor(wanted + 0.5))))


def keys_for(view, chart, dpi_scale=1.0):
    """(zoom, x, y) of every tile of `chart` under the view, or [] when the chart does not draw it."""
    if chart not in CHARTS:
        return []
    tz = chart_zoom(chart, view.zoom, dpi_scale)
    if tz is None:
        return []
    span = TILE_PX * 2 ** (view.zoom - tz)
    count = 2 ** tz
    x0, x1 = int(math.floor(view.left / span)), int(math.floor((view.left + view.width) / span))
    y0, y1 = int(math.floor(view.top / span)), int(math.floor((view.top + view.height) / span))
    keys = [(tz, x % count, y) for y in range(max(0, y0), min(count - 1, y1) + 1) for x in range(x0, x1 + 1)]
    return keys if len(keys) <= MOST_TILES else []


class ChartSource:
    """Chart tiles from their own servers: `fetch(url)` is an awaitable of a tile's bytes, b'' for a square the chart
    has nothing in (server.HomeAssistant.chart_tile), injected so the tests need no network."""

    def __init__(self, fetch, clock=time.monotonic):
        self.fetch, self.clock = fetch, clock
        self.raw = OrderedDict()       # (chart, z, x, y) -> (bytes, fetched at)
        self.bytes = 0
        self.quiet_until = {}          # chart -> when it may be asked again
        self.gate = asyncio.Semaphore(MAX_CONCURRENT)
        self.pending = {}

    def available(self, chart):
        return self.clock() >= self.quiet_until.get(chart, 0.0)

    def _keep(self, key, raw):
        if key in self.raw:
            self.bytes -= len(self.raw.pop(key)[0])
        self.raw[key] = (raw, self.clock())
        self.bytes += len(raw)
        while self.bytes > CACHE_BYTES and self.raw:
            _, (old, _) = self.raw.popitem(last=False)
            self.bytes -= len(old)

    async def _fetch(self, key):
        chart, z, x, y = key
        async with self.gate:
            raw = await self.fetch(CHARTS[chart]['url'].format(z=z, x=x, y=y))
        if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_TILE_BYTES:
            raise ValueError('not a tile')
        self._keep(key, bytes(raw))
        return bytes(raw)

    async def tile(self, chart, z, x, y):
        key = (chart, z, x, y)
        low, high = CHARTS[chart]['zoom']
        if any(type(n) is not int for n in (z, x, y)) or not low <= z <= high or not 0 <= x < (1 << z) or not 0 <= y < (1 << z):
            return b''
        found = self.raw.get(key)
        if found and self.clock() - found[1] < TILE_TTL:
            self.raw.move_to_end(key)
            return found[0]
        if key in self.pending:
            return await self.pending[key]
        task = asyncio.ensure_future(self._fetch(key))
        self.pending[key] = task
        try:
            return await task
        finally:
            self.pending.pop(key, None)

    async def tiles(self, chart, keys):
        """{(z, x, y): bytes} of the tiles that came (b'' where the chart has nothing); {} while its server gives none."""
        if not keys or chart not in CHARTS or not self.available(chart):
            return {}
        results = await asyncio.gather(*(self.tile(chart, *key) for key in keys), return_exceptions=True)
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors and len(errors) == len(results):
            self.quiet_until[chart] = self.clock() + COOLDOWN
            LOG.info('The %s chart did not come (%s): its map cards are drawn with streets, and the app asks again in %d '
                     'minutes', chart, type(errors[0]).__name__, COOLDOWN // 60)
            return {}
        if errors:
            LOG.info('%d of %d %s chart tiles did not come (%s)', len(errors), len(results), chart, type(errors[0]).__name__)
        return {key: r for key, r in zip(keys, results) if not isinstance(r, BaseException)}


def drawable(tiles):
    """Whether any of the tiles that came has a picture: none means the card is outside the chart."""
    return any(tiles.values())
