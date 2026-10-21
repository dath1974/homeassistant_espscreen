"""A map centred on an airport by its code (docs/MAP.md, "A place of its own"): OurAirports' list in the app
(tools/build_airports.py), a code meaning the field it names first, and the layout keeping the code itself."""
import gzip
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import airports  # noqa: E402
import map_card  # noqa: E402
from core import validate_layout  # noqa: E402


def save(**options):
    return validate_layout({'title': 'x', 'tiles': [{'entity': 'screen.map', 'options': {'display': 'map', 'framing': 'place', **options}}]})['tiles'][0]['options']


class Lookup(unittest.TestCase):
    def test_the_list_knows_airports_by_every_code_they_go_by(self):
        cases = {'KJFK': 'John F. Kennedy International Airport', 'JFK': 'John F. Kennedy International Airport',
                 'EGLL': 'London Heathrow Airport', 'LHR': 'London Heathrow Airport', 'EHAM': 'Amsterdam Airport Schiphol',
                 'ams': 'Amsterdam Airport Schiphol', 'RJTT': 'Tokyo Haneda International Airport',
                 # Haneda's IATA code is a Mexican heliport's local code too: the airport it names first.
                 'HND': 'Tokyo Haneda International Airport',
                 # A small field by its FAA code, letters and digits.
                 '00AA': 'Aero B Ranch Airport'}
        for code, name in cases.items():
            with self.subTest(code=code):
                found = airports.find(code)
                self.assertEqual((found['code'], found['name']), (code.upper(), name))
        self.assertAlmostEqual(airports.find('KJFK')['lat'], 40.6394, places=3)
        for wrong in ('ZZZZQ', '', ' ', 'two words', 'KJFK!', None, 12):
            self.assertIsNone(airports.find(wrong), wrong)

    def test_a_code_two_fields_share_means_its_own_one_and_the_larger(self):
        lines = ['\t'.join(row) for row in (
            # ident, icao, iata, gps, local, kind, lat, lon, name
            ('MX-1', '', '', '', 'ABC', '4', '1', '1', 'A heliport whose local code is ABC'),
            ('KABC', '', 'ABC', '', '', '2', '2', '2', 'A small airport whose IATA code is ABC'),
            ('ZZ01', '', '', 'ABC', '', '4', '3', '3', 'A heliport whose GPS code is ABC'),
            ('XYZ', '', '', '', '', '2', '4', '4', 'A small field called XYZ'),
            ('KXYZ', '', '', '', 'XYZ', '0', '5', '5', 'A large airport whose local code is XYZ'),
            ('LOC1', '', '', '', 'LOC', '2', '6', '6', 'A small field whose local code is LOC'),
            ('LOC2', '', '', '', 'LOC', '0', '7', '7', 'A large one with the same local code'))]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'airports.tsv.gz'
            with gzip.open(path, 'wt', encoding='utf-8') as out:
                out.write('\n'.join(lines) + '\n')
            with mock.patch.object(airports, 'FILE', path):
                airports.find.cache_clear()
                try:
                    self.assertEqual(airports.find('ABC')['lat'], 3, 'a field\'s own code before an IATA or local one')
                    self.assertEqual(airports.find('XYZ')['lat'], 4, 'its own ident, however small')
                    self.assertEqual(airports.find('LOC')['lat'], 7, 'the larger of two that share a local code')
                finally:
                    airports.find.cache_clear()


class Layout(unittest.TestCase):
    def test_a_code_is_kept_as_typed_in_capitals_and_drawn_where_the_airport_is(self):
        options = save(centre='egll')
        self.assertEqual(options['centre'], 'EGLL')
        lat, lon = map_card.centre_of({'options': options})
        self.assertAlmostEqual(lat, 51.4708, places=3)
        self.assertAlmostEqual(lon, -0.4599, places=3)
        self.assertEqual(save(centre=[40.64, -73.78])['centre'], [40.64, -73.78], 'a latitude and longitude as before')

    def test_an_unknown_code_is_refused(self):
        for wrong in ('ZZZZQ', 'two words', '', 'K'):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                save(centre=wrong)

    def test_a_code_the_list_no_longer_knows_centres_on_home(self):
        self.assertIsNone(map_card.centre_of({'options': {'centre': 'ZZZZQ'}}))
        home = map_card.Zone('zone.home', 'Home', 52.0, 5.0, 100)
        view = map_card.frame_view('place', 'town', [], [home], (400, 300), centre=map_card.centre_of({'options': {'centre': 'ZZZZQ'}}))
        self.assertEqual((view.lat, view.lon), (52.0, 5.0))


if __name__ == '__main__':
    unittest.main()
