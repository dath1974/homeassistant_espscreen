#!/usr/bin/env python3
"""Write screen_manager/app/airports.tsv.gz, the airports a map can be centred on by their code (airports.py).

From OurAirports (https://ourairports.com/data/, public domain): every airport, heliport and seaplane base that is not
closed, with the codes it goes by (its own ident, ICAO, IATA, GPS and local code), the kind of field it is, where it
is and its name. Run it now and then, as at a release:

    python3 tools/build_airports.py                 # downloads airports.csv
    python3 tools/build_airports.py airports.csv    # or reads one already downloaded
"""
import csv
import gzip
import io
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'screen_manager/app/airports.tsv.gz'
SOURCE = 'https://davidmegginson.github.io/ourairports-data/airports.csv'
# The kind of field, the first the one a code means when two share it (airports.py).
KINDS = ('large_airport', 'medium_airport', 'small_airport', 'seaplane_base', 'heliport')
NAME_MOST = 60


def rows(text):
    for row in csv.DictReader(io.StringIO(text)):
        if row['type'] not in KINDS:
            continue
        try:
            lat, lon = float(row['latitude_deg']), float(row['longitude_deg'])
        except ValueError:
            continue
        codes = [row[key].strip().upper() for key in ('ident', 'icao_code', 'iata_code', 'gps_code', 'local_code')]
        if not any(codes):
            continue
        # A code the same as the field's own ident is left blank: airports.py reads a blank as the ident.
        codes = codes[:1] + ['' if code == codes[0] else code for code in codes[1:]]
        name = ' '.join(row['name'].split())[:NAME_MOST]
        yield [*codes, str(KINDS.index(row['type'])), f'{lat:.5f}', f'{lon:.5f}', name]


def main():
    if len(sys.argv) > 1:
        text = Path(sys.argv[1]).read_text(encoding='utf-8')
    else:
        with urllib.request.urlopen(urllib.request.Request(SOURCE, headers={'User-Agent': 'ESP Screens build'}), timeout=120) as response:
            text = response.read().decode('utf-8')
    lines = ['\t'.join(row) for row in rows(text)]
    lines.sort()
    # mtime 0: the same list writes the same file.
    with open(OUT, 'wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0, filename='') as out:
        out.write(('\n'.join(lines) + '\n').encode('utf-8'))
    print(f'wrote {OUT.relative_to(ROOT)}: {len(lines)} fields, {OUT.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
