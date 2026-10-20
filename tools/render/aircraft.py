"""Render aircraft over map tiles (docs/MAP.md, "Aircraft") with the real firmware on the host (tools/render/host.py)
and the add-on's own aircraft.py: planes as a dot, a dot with its heading and a plane, their labels and tracks, on a
square card, two single cards and the full view, light and dark, and each card again after 20 s more of flight.

    python3 tools/render/aircraft.py guition waveshare43 [--tiles DIR]

It is map_tiles.py's study with a source of flights: the program asks for its map cards' planes the way it asks ESP
Screens (esphome.screen_camera with `air`), and this script answers as server.Manager.answer_air does. The planes are
made up, flying round the household of map_tiles.py in Amsterdam.
"""
import argparse
import asyncio
import math
import os
import shlex
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import map_tiles  # noqa: E402
import run  # noqa: E402
import host  # noqa: E402
import aircraft  # noqa: E402
import core  # noqa: E402
import map_card  # noqa: E402
import send_layout  # noqa: E402

SOURCE = 'sensor.flightradar24_current_in_area'
# id, callsign, type, latitude, longitude, feet, heading, knots, from, to, on the ground
PLANES = [
    ('a1', 'KLM1234', 'B738', 52.335, 4.835, 3500, 230, 180, 'LHR', 'AMS', False),
    ('a2', 'EZY45AB', 'A320', 52.392, 4.795, 12000, 60, 290, 'AMS', 'BER', False),
    ('a3', 'BAW432', 'A321', 52.300, 4.960, 24000, 280, 420, 'FRA', 'LHR', False),
    ('a4', 'DLH9KM', 'A20N', 52.420, 4.950, 36000, 110, 460, 'DUB', 'MUC', False),
    ('a5', 'TRA6312', 'B738', 52.310, 4.765, 0, 180, 12, 'AMS', 'AGP', True),
    ('a6', 'RYR8812', 'B38M', 52.250, 4.860, 31000, 10, 440, 'BCN', 'OSL', False),
]
NOW = 1000.0


def state_at(seconds):
    """The source's state `seconds` from now: every plane further along its heading."""
    flights = []
    for key, callsign, model, lat, lon, feet, heading, knots, origin, destination, ground in PLANES:
        metres = knots * 0.514444 * seconds
        lat2 = lat + metres * math.cos(math.radians(heading)) / 111320
        lon2 = lon + metres * math.sin(math.radians(heading)) / (111320 * math.cos(math.radians(lat)))
        flights.append({'id': key, 'callsign': callsign, 'aircraft_code': model, 'latitude': lat2, 'longitude': lon2,
                        'altitude': feet, 'heading': heading, 'ground_speed': knots, 'airport_origin_code_iata': origin,
                        'airport_destination_code_iata': destination, 'on_ground': 1 if ground else 0})
    return {'state': str(len(flights)), 'attributes': {'friendly_name': 'Current in area', 'flights': flights}}


# Holding between reports: a render waits for two snapshots alike, which planes that glide never give (the glide itself
# is tests/test_aircraft_plan.cpp's).
AROUND = {'framing': 'home', 'distance': 'region', 'aircraft': SOURCE, 'follow': 'chosen', 'plane_motion': 'hold'}
# The pages map_tiles drives: its names are the ones it opens over the whole glass with a tap.
PAGES = [
    ('square', [('screen.map', 'Overhead', 'square', {**AROUND, 'plane_marker': 'plane', 'plane_track': 'show', 'plane_track_s': 120})]),
    ('singles', [('screen.map', 'Dots', 'single', {**AROUND, 'plane_track': 'show'}),
                 ('screen.map', 'Arrows', 'single', {**AROUND, 'plane_marker': 'arrow', 'plane_label': 'callsign', 'plane_colour': 'accent'})]),
]


class Study(map_tiles.Study):
    def __init__(self, *args):
        super().__init__(*args)
        self.tracks, self.now, self.asked = aircraft.Tracks(), NOW, {}
        for seconds in range(-120, 1, 10):
            self.tracks.update(SOURCE, aircraft.flights_of(state_at(seconds)), NOW + seconds)
        map_tiles.STATES[SOURCE] = state_at(0)

    def answer(self, call):
        if call.service == 'esphome.screen_camera' and 'air' in call.data:
            data = dict(call.data)
            self.asked[data['air']] = data
            task = asyncio.get_running_loop().create_task(self.air(data))
            task.add_done_callback(lambda t: t.exception() and self.warnings.append(f'air failed: {t.exception()!r}'))
            return
        super().answer(call)

    async def air(self, data):
        """As server.Manager.answer_air answers: the planes of each card on the view its picture shows."""
        full = data['air'] == 'full'
        for index, size in aircraft.cards_of(data, 4096):
            tile = self.compiled[index]
            move = data.get('move', '') if full else ''
            view = map_card.view_for(tile, map_tiles.STATES, size, self.board, None, full, data.get('focus') or None,
                                     map_card.move_of(move) if full else None)
            options = aircraft.options_of(tile)
            planes = aircraft.overlay(view, aircraft.flights_of(map_tiles.STATES[SOURCE]), options, self.tracks, SOURCE, size,
                                      self.board.scale, full, False, self.now)
            message = aircraft.message(data['air'], index, size, planes, aircraft.style_of(options), move, data.get('focus', ''))
            async with self.turn:
                await self.send(message)

    async def until(self, found, *args, **kwargs):
        # map_tiles waits for the full view's "Downloading image"; the loader now says "camera: loaded".
        return await super().until(lambda line: found(line) or 'camera: loaded' in line, *args, **kwargs)

    async def picture(self, what, tries=4):
        await super().picture(what, tries)
        # The card asks for its planes once its picture is on the glass (air_tick, every 250 ms).
        await asyncio.sleep(1.5)

    async def render(self, name, keep=True, timeout=25):
        await super().render(name, keep, timeout)
        if name.endswith('-later'):
            return
        # 20 s on: the source reports again, and the planes move on every card that asked, with their tracks.
        self.now += 20
        map_tiles.STATES[SOURCE] = state_at(self.now - NOW)
        self.tracks.update(SOURCE, aircraft.flights_of(map_tiles.STATES[SOURCE]), self.now)
        for data in list(self.asked.values()):
            await self.air(data)
        await asyncio.sleep(1.2)
        await super().render(f'{name}-later', keep, timeout)
        # Back as it was, for the next shot.
        self.now = NOW
        map_tiles.STATES[SOURCE] = state_at(0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('variants', nargs='+')
    parser.add_argument('--out', type=Path, default=run.REPO / '.esphome' / 'aircraft' / 'out')
    parser.add_argument('--tiles', type=Path, help='a folder of Home Assistant vector tiles, z_x_y.mvt')
    args = parser.parse_args()
    args.out = args.out.resolve()
    map_tiles.PAGES[:] = PAGES
    # Each tile's state with its extras, as the add-on sends it: a map tile's mark and `air`, which makes it ask for planes.
    plain = send_layout.state_message
    send_layout.state_message = lambda i, tile, states: plain(i, tile, states, core.extras(tile, states))
    esphome = shlex.split(os.environ.get('ESPHOME', 'esphome'))
    streets = map_tiles.streets_from(args.tiles)
    pictures = run.Pictures()
    for key in args.variants:
        item = host.variant(key)
        build = host.Build(item, tree=run.REPO, work=None, esphome=esphome)
        started = time.monotonic()
        ok, output = build.compile()
        if not ok:
            print(f'{key}: BUILD FAILED\n{output[-3000:]}', flush=True)
            continue
        study = Study(build, args.out / key, pictures, streets)
        try:
            summary = asyncio.run(study.run())
        except Exception as error:
            summary = f'stopped: {type(error).__name__}: {error}'
        print(f'{key}: {summary} ({time.monotonic() - started:.0f} s) {study.warnings}', flush=True)


if __name__ == '__main__':
    main()
