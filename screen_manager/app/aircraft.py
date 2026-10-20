"""Aircraft over a map tile (docs/MAP.md, "Aircraft"): the flights a Home Assistant sensor lists, drawn by the screen
over the map's picture and moved in place as the sensor reports them.

The street map stays the picture the add-on draws (map_card.py) and never changes for an aircraft. The planes go to the
screen as a small message of pixels on that picture (op "air"), sent again on every report of the sensor, so they move
without a new picture. Where a plane is stays in the add-on; the screen gets where it stands on the glass, which way it
flies and how fast in pixels, its label and its track.

A source is any sensor whose `flights` attribute lists the aircraft with their `latitude` and `longitude`, as the
Flightradar24 integration's "Current in area" sensor does (github.com/AlexandrErohin/home-assistant-flightradar24). Its
other fields (`altitude` in feet, `heading`, `ground_speed` in knots, `callsign`, `aircraft_registration`, ...) are read
when they are there.

Watched aircraft (`plane_watch`) are registrations or callsigns with a colour each: a plane that matches one is shown
whatever its altitude, on the ground or not and however many others there are, always with its label, in its colour.

The track is the add-on's own: every report adds each plane's place with its moment, so a track of 60 seconds is the
last minute of that plane, whatever the source keeps of its own.
"""
import json
import math
import re
import time

import catalogue
import map_card

SOURCE_ATTRIBUTE = 'flights'
# The name a screen that draws aircraft gives in its hello's features.
FEATURE = 'aircraft'
SOURCE = re.compile(r'sensor\.[a-z0-9_]+')
MAP_TILE = 'screen.map'

# The choices of a map tile's aircraft (catalogue/person.yaml `map.aircraft`): a list of words, the first the default,
# or [default, lowest, highest] of a whole number (the track's length in seconds, the most planes on the card, the
# altitudes in feet a plane is shown between, the highest meaning every altitude).
AIRCRAFT = catalogue.of_type('person')['map']['aircraft']
NUMBERS = {key: tuple(value) for key, value in AIRCRAFT.items() if all(isinstance(v, int) for v in value)}
CHOICES = {key: tuple(value) for key, value in AIRCRAFT.items() if key not in NUMBERS}
ALTITUDE_CEILING = NUMBERS['plane_max'][2]
# Watched aircraft (catalogue/person.yaml `map.watch`): [{"id": registration or callsign, "colour": one of COLOURS}].
# On the wire a plane's colour is its place in COLOURS plus one, 0 for a plane nobody watches.
WATCH = catalogue.of_type('person')['map']['watch']
WATCH_COLOURS, WATCH_MOST = tuple(WATCH['colours']), WATCH['max']
WATCH_ID = re.compile(r'[A-Z0-9-]{2,10}')
OWN = ('aircraft', *CHOICES, *NUMBERS, 'plane_watch')

# Altitude bands the screen colours a marker by (tar1090's rainbow, in the screen's own colours, theme.h AIRCRAFT_*):
# on the ground, below 5,000 ft, below 15,000, below 30,000, and above.
BANDS = (5000, 15000, 30000)

# What one message may hold: the screen takes 4096 bytes (page_receiver.cpp), its envelope and the session's keys take
# the rest.
MESSAGE_BYTES = 3400
TRACK_POINTS = 10
# A plane is still shown this far beyond the frame, so one that flies in is there at once.
MARGIN = 24
# A plane the source stopped listing is forgotten after this long, and with it its track.
FORGET_SECONDS = 120


class Flight:
    __slots__ = ('id', 'lat', 'lon', 'altitude', 'heading', 'speed', 'callsign', 'model', 'origin', 'destination',
                 'on_ground', 'airline', 'registration', 'flight')

    def __init__(self, id, lat, lon, altitude=None, heading=None, speed=None, callsign='', model='', origin='',
                 destination='', on_ground=False, airline='', registration='', flight=''):
        self.id, self.lat, self.lon = id, lat, lon
        self.altitude, self.heading, self.speed = altitude, heading, speed
        self.callsign, self.model, self.origin, self.destination = callsign, model, origin, destination
        self.on_ground, self.airline, self.registration, self.flight = on_ground, airline, registration, flight


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value, most=24):
    return str(value).strip()[:most] if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip() else ''


def flights_of(state):
    """The aircraft a source's state lists, each with a place: Flightradar24's fields, read where they are."""
    listed = ((state or {}).get('attributes') or {}).get(SOURCE_ATTRIBUTE)
    if not isinstance(listed, list):
        return []
    out, seen = [], set()
    for item in listed:
        if not isinstance(item, dict):
            continue
        lat, lon = _number(item.get('latitude')), _number(item.get('longitude'))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        callsign = _text(item.get('callsign'), 12) or _text(item.get('flight_number'), 12)
        key = _text(item.get('id'), 32) or _text(item.get('aircraft_icao_24bit'), 12) or callsign
        if not key or key in seen:
            continue
        seen.add(key)
        heading = _number(item.get('heading'))
        out.append(Flight(key, lat, lon, _number(item.get('altitude')), heading % 360 if heading is not None else None,
                          _number(item.get('ground_speed')), callsign,
                          _text(item.get('aircraft_code'), 8) or _text(item.get('aircraft_model'), 16),
                          _text(item.get('airport_origin_code_iata'), 4), _text(item.get('airport_destination_code_iata'), 4),
                          item.get('on_ground') in (True, 1, '1'), _text(item.get('airline_short'), 20),
                          _text(item.get('aircraft_registration'), 12) or _text(item.get('registration'), 12),
                          _text(item.get('flight_number'), 12)))
    return out


def sources(states):
    """The sensors a map tile can take its aircraft from, by name: those whose `flights` attribute is a list."""
    found = []
    for entity, state in states.items():
        if not isinstance(entity, str) or not entity.startswith('sensor.'):
            continue
        a = (state or {}).get('attributes') or {}
        if isinstance(a.get(SOURCE_ATTRIBUTE), list):
            found.append({'id': entity, 'name': a.get('friendly_name') or entity.split('.', 1)[1], 'state': state.get('state')})
    return sorted(found, key=lambda item: item['name'].lower())


def options_of(tile):
    """Every aircraft choice of a map tile, a stored one or its default; `aircraft` its source, '' for none."""
    options = tile.get('options') or {}
    out = {'aircraft': options.get('aircraft') if isinstance(options.get('aircraft'), str) else ''}
    for key, choices in CHOICES.items():
        out[key] = options.get(key) if options.get(key) in choices else choices[0]
    for key, (default, low, high) in NUMBERS.items():
        value = options.get(key)
        out[key] = value if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high else default
    out['plane_watch'] = watched_of(options.get('plane_watch'))
    return out


def watch_key(text):
    """A registration or callsign as it is compared: capitals and digits only, so G-EZAB is GEZAB."""
    return re.sub(r'[^A-Z0-9]', '', str(text).upper())


def watched_of(value):
    """{watch_key: colour on the wire} of a tile's watched aircraft, the first entry of a key winning."""
    out = {}
    for item in value if isinstance(value, list) else ():
        if isinstance(item, dict) and isinstance(item.get('id'), str) and item.get('colour') in WATCH_COLOURS:
            key = watch_key(item['id'])
            if key and key not in out:
                out[key] = WATCH_COLOURS.index(item['colour']) + 1
    return out


def watch_colour(flight, watched):
    """The colour on the wire of a plane someone watches, by its registration, callsign or flight number; 0 for none."""
    for text in (flight.registration, flight.callsign, flight.flight):
        if text and watched.get(watch_key(text)):
            return watched[watch_key(text)]
    return 0


def source_of(tile):
    """The sensor a map tile's aircraft come from, '' for a tile without aircraft or one that shows its people only."""
    if tile.get('entity') != MAP_TILE or map_card.options_of(tile)['show'] == 'people':
        return ''
    return options_of(tile)['aircraft']


def validate(options):
    """A map tile's aircraft choices checked, with the defaults left out as the layout stores them. Raises ValueError
    with the setting that is wrong."""
    out = dict(options)
    source = out.get('aircraft')
    if source == '':
        out.pop('aircraft')
    elif source is not None and (not isinstance(source, str) or len(source) > 255 or not SOURCE.fullmatch(source)):
        raise ValueError('aircraft')
    for key, choices in CHOICES.items():
        if key in out:
            if out[key] not in choices:
                raise ValueError(key)
            if out[key] == choices[0]:
                out.pop(key)
    for key, (default, low, high) in NUMBERS.items():
        if key in out:
            value = out[key]
            if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
                raise ValueError(key)
            if value == default:
                out.pop(key)
    if out.get('plane_min', 0) > out.get('plane_max', ALTITUDE_CEILING):
        raise ValueError('plane_min')
    if 'plane_watch' in out:
        listed = out['plane_watch']
        if not isinstance(listed, list) or len(listed) > WATCH_MOST:
            raise ValueError('plane_watch')
        kept, seen = [], set()
        for item in listed:
            if not isinstance(item, dict) or set(item) != {'id', 'colour'} or not isinstance(item['id'], str) \
                    or item['colour'] not in WATCH_COLOURS:
                raise ValueError('plane_watch')
            name = item['id'].strip().upper()
            if not WATCH_ID.fullmatch(name) or not watch_key(name):
                raise ValueError('plane_watch')
            if watch_key(name) not in seen:
                seen.add(watch_key(name))
                kept.append({'id': name, 'colour': item['colour']})
        if kept:
            out['plane_watch'] = kept
        else:
            out.pop('plane_watch')
    return out


class Tracks:
    """Where each plane of each source has been, with the moment, so a track is the last N seconds of it."""

    def __init__(self, keep=NUMBERS['plane_track_s'][2]):
        self.keep = keep
        self.seen = {}

    def update(self, source, flights, now=None):
        now = time.monotonic() if now is None else now
        planes = self.seen.setdefault(source, {})
        for flight in flights:
            points = planes.setdefault(flight.id, [])
            if not points or (points[-1][1], points[-1][2]) != (flight.lat, flight.lon):
                points.append((now, flight.lat, flight.lon))
        for key in list(planes):
            points = [p for p in planes[key] if now - p[0] <= self.keep]
            if not points or now - points[-1][0] > FORGET_SECONDS:
                del planes[key]
            else:
                planes[key] = points

    def of(self, source, key, seconds, now=None):
        """The places of one plane within the last `seconds`, oldest first."""
        now = time.monotonic() if now is None else now
        return [(lat, lon) for moment, lat, lon in self.seen.get(source, {}).get(key, ()) if now - moment <= seconds]

    def forget(self, keep_sources):
        for source in [s for s in self.seen if s not in keep_sources]:
            del self.seen[source]


def band(flight):
    """0 on the ground, then one more for each of BANDS a plane flies above; None without an altitude."""
    if flight.on_ground:
        return 0
    if flight.altitude is None:
        return None
    return 1 + sum(flight.altitude >= limit for limit in BANDS)


def shown(flights, options, view):
    """The planes a card shows: within its altitudes, on the ground only when asked, inside the frame, the closest to
    its middle first, at most `plane_most`; and after them every watched plane inside the frame, whatever the rest says."""
    low, high = options['plane_min'], options['plane_max']
    watched = options.get('plane_watch') or {}
    out, picked = [], []
    for flight in flights:
        if watched and watch_colour(flight, watched):
            x, y = view.point(flight.lat, flight.lon)
            if -MARGIN <= x <= view.width + MARGIN and -MARGIN <= y <= view.height + MARGIN:
                picked.append(flight)
            continue
        if flight.on_ground and options['plane_ground'] == 'hide':
            continue
        if not flight.on_ground and flight.altitude is not None and not low <= flight.altitude <= high:
            continue
        # A plane without an altitude is shown only when the card takes every altitude.
        if flight.altitude is None and not flight.on_ground and (low > 0 or high < ALTITUDE_CEILING):
            continue
        x, y = view.point(flight.lat, flight.lon)
        if -MARGIN <= x <= view.width + MARGIN and -MARGIN <= y <= view.height + MARGIN:
            out.append((math.hypot(x - view.width / 2, y - view.height / 2), flight))
    out.sort(key=lambda item: item[0])
    return [flight for _, flight in out[:options['plane_most']]] + picked


def label_kind(options, size, scale, full):
    """What a plane's label says: the choice, or for `auto` what the card has room for."""
    kind = options['plane_label']
    if kind != 'auto':
        return kind
    if full:
        return 'altitude'
    small = min(size)
    return 'none' if small < 140 * scale else 'callsign' if small < 260 * scale else 'altitude'


def altitude_text(flight, metric, number=str, suffix=lambda unit: ' ' + unit):
    if flight.on_ground:
        return ''
    if flight.altitude is None:
        return ''
    if metric:
        return number(str(round(flight.altitude * 0.3048 / 10) * 10)) + suffix('m')
    return number(str(round(flight.altitude / 100) * 100)) + suffix('ft')


def speed_text(flight, metric, number=str, suffix=lambda unit: ' ' + unit):
    if flight.speed is None:
        return ''
    return number(str(round(flight.speed * 1.852))) + suffix('km/h') if metric else number(str(round(flight.speed))) + suffix('kn')


def label_of(flight, kind, metric, number=str, suffix=lambda unit: ' ' + unit):
    """A plane's label, its lines joined by a newline: the callsign, then its altitude, then its speed, type and route."""
    if kind == 'none':
        return ''
    name = flight.callsign or flight.registration or flight.model or flight.id
    if kind == 'callsign':
        return name[:12]
    altitude = altitude_text(flight, metric, number, suffix)
    if kind == 'altitude':
        return '\n'.join(part for part in (name[:12], altitude) if part)
    first = ' · '.join(part for part in (name[:12], flight.model[:8]) if part)
    second = ' · '.join(part for part in (altitude, speed_text(flight, metric, number, suffix)) if part)
    route = f'{flight.origin} → {flight.destination}' if flight.origin and flight.destination else ''
    return '\n'.join(part for part in (first, second, route) if part)


def velocity(flight, view):
    """Where a plane goes in a minute on the frame, in pixels: its heading and ground speed at the view's zoom."""
    if flight.on_ground or flight.speed is None or flight.heading is None:
        return 0, 0
    per_minute = flight.speed * 0.514444 * 60 / map_card.metres_per_pixel(flight.lat, view.zoom)
    angle = math.radians(flight.heading)
    return round(math.sin(angle) * per_minute), round(-math.cos(angle) * per_minute)


def thin(points, most):
    """At most `most` points of a track, the first and the last kept, the rest evenly between."""
    if len(points) <= most:
        return points
    step = (len(points) - 1) / (most - 1)
    return [points[round(n * step)] for n in range(most)]


def overlay(view, flights, options, tracks=None, source='', size=None, scale=1.0, full=False, metric=False, now=None,
            number=str, suffix=lambda unit: ' ' + unit):
    """The planes of one card on its frame: [x, y, heading, band, vx, vy, label, track, watched], with -1 for a heading
    or band it has none of, the track as x, y, x, y ... oldest first, ending where the plane is, and `watched` the colour
    of a watched plane (watch_colour), which comes last so the screen draws it on top, always with a label."""
    size = size or (view.width, view.height)
    kind = label_kind(options, size, scale, full)
    watched = options.get('plane_watch') or {}
    out = []
    for flight in shown(flights, options, view):
        colour = watch_colour(flight, watched) if watched else 0
        x, y = view.point(flight.lat, flight.lon)
        vx, vy = velocity(flight, view) if options['plane_motion'] == 'glide' else (0, 0)
        track = []
        if options['plane_track'] == 'show' and tracks is not None:
            places = tracks.of(source, flight.id, options['plane_track_s'], now)
            for lat, lon in thin(places, TRACK_POINTS):
                px, py = view.point(lat, lon)
                track += [round(px), round(py)]
        level = band(flight)
        out.append([round(x), round(y), round(flight.heading) if flight.heading is not None else -1,
                    -1 if level is None else level, vx, vy,
                    label_of(flight, 'callsign' if colour and kind == 'none' else kind, metric, number, suffix), track, colour])
    return out


def style_of(options):
    """How the screen draws every plane of a card: its marker, its colour and whether it glides between reports."""
    return {'m': options['plane_marker'], 'c': options['plane_colour'], 'g': 1 if options['plane_motion'] == 'glide' else 0}


def cards_of(request, most):
    """[(tile index, (width, height))] a screen's ask names (server.answer_air): `cards` "3:180x120,5:400x300" for the
    tiles of the page on the glass, or `idx` and `size` "800x480" for the full view; each size at most `most` a side."""
    def size_of(text):
        width, _, height = text.partition('x')
        if not (width.isdigit() and height.isdigit() and len(width) <= 5 and len(height) <= 5):
            return None
        width, height = int(width), int(height)
        return (width, height) if 1 <= width <= most and 1 <= height <= most else None
    out = []
    if request.get('air') == 'full':
        index, size = request.get('idx'), request.get('size')
        if isinstance(index, str) and index.isdigit() and len(index) <= 3 and isinstance(size, str) and size_of(size):
            out.append((int(index), size_of(size)))
        return out
    cards = request.get('cards')
    if not isinstance(cards, str) or len(cards) > 200:
        return out
    for part in cards.split(','):
        index, _, size = part.partition(':')
        if index.isdigit() and len(index) <= 3 and size_of(size) and all(i != int(index) for i, _ in out):
            out.append((int(index), size_of(size)))
    return out[:8]


def message(target, index, size, planes, style, move='', focus=''):
    """The op "air" for one card, made to fit what the screen takes: the farthest planes go first, then the tracks are
    thinned. `target` is "tile" (a card of the page, `index` its tile) or "full" (the full view of tile `index`), `size`
    the picture's pixels the planes are placed on."""
    planes = [list(p) for p in planes]
    body = {'v': 1, 'op': 'air', 't': target, 'i': index, 'w': size[0], 'h': size[1], 's': style, 'a': planes}
    if target == 'full':
        body['mv'], body['f'] = move, focus

    def length():
        return len(json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode())
    while length() > MESSAGE_BYTES and any(len(p[7]) > 4 for p in planes):
        for p in planes:
            points = len(p[7]) // 2
            if points > 2:
                p[7] = [v for pair in thin([(p[7][2 * n], p[7][2 * n + 1]) for n in range(points)], max(2, points // 2)) for v in pair]
    # The farthest plane nobody watches goes first; a watched one only when nothing else is left.
    while length() > MESSAGE_BYTES and planes:
        unwatched = [n for n, p in enumerate(planes) if len(p) < 9 or not p[8]]
        planes.pop(unwatched[-1] if unwatched else -1)
    return body
