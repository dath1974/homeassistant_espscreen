"""Airports by their code, for a map centred on one (map_card.centre_of, docs/MAP.md "Centre on").

airports.tsv.gz is written by tools/build_airports.py from OurAirports (public domain): one field a line, its ident,
ICAO, IATA, GPS and local code (a blank one the same as its ident), its kind (0 a large airport up to 4 a heliport),
latitude, longitude and name. Nothing is asked of the internet.

A code can mean more than one field: HND is Tokyo's Haneda by its IATA code and a heliport in Mexico by its local
one. A field's own ident, ICAO or GPS code goes before an IATA or local code, and a larger field before a smaller one.
The file is read through for each code asked and the answer kept, so the list never sits in memory.
"""
from functools import lru_cache
import gzip
from pathlib import Path
import re

FILE = Path(__file__).resolve().parent / 'airports.tsv.gz'
# What a code looks like: letters, digits and a dash (OurAirports' own idents, such as US-1234), 2 to 10 long.
CODE = re.compile(r'^[A-Z0-9][A-Z0-9-]{1,9}$')


def code_of(text):
    """`text` as a code to look up (upper case, trimmed), or None when it cannot be one."""
    if not isinstance(text, str):
        return None
    code = text.strip().upper()
    return code if CODE.match(code) else None


@lru_cache(maxsize=256)
def find(code):
    """{'code', 'name', 'lat', 'lon'} of the field `code` means, or None."""
    code = code_of(code)
    if code is None or not FILE.exists():
        return None
    best = None
    with gzip.open(FILE, 'rt', encoding='utf-8') as lines:
        for line in lines:
            if code not in line:
                continue
            parts = line.rstrip('\n').split('\t')
            if len(parts) != 9:
                continue
            ident, icao, iata, gps, local, kind, lat, lon, name = parts
            if code in (ident, icao, gps):
                tier = 0
            elif code in (iata, local):
                tier = 1
            else:
                continue
            rank = (tier, int(kind))
            if best is None or rank < best[0]:
                best = (rank, {'code': code, 'name': name, 'lat': float(lat), 'lon': float(lon)})
    return best[1] if best else None
