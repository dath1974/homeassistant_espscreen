# A map card

Tessera can show a map of where people are: the streets around them, your zones, and a marker for everyone on the
card. Tessera draws the whole card in the screen's own colours and sends the screen a picture, the way a live camera
arrives. The screen never gets a location.

There are two kinds of map:

- **A person's map** (app 0.4.33, firmware 0.20.0): set a `person.*` tile's **Display** to **Map**. It follows that
  person, and whoever you add under **Also on the map**.
- **The map tile** (app 0.4.36, firmware 0.21.0): **Map** under the screen's own cards in the library. It belongs to
  no one: it follows **everyone** Home Assistant knows the place of, or only the people and trackers you choose. Just
  the two of you, or only your devices.

Both work on every tile size, from one cell to the whole page, on every board that draws pictures (the boards with
`camera` in `screen_manager/app/boards.json`). The CYD and the other boards without memory for pictures do not offer them,
and a layout with one is refused on them.

**A tap opens the map over the whole screen**, as a camera tile does: drawn as large as the board takes a camera picture,
with the round back key and the tile's name at the top. A small 1 x 1 map you glance at becomes a full map with a tap.

**On the full map, tap a person or a tracker** to focus on them, as Home Assistant's own map does: they stay exactly on
their place in the middle, closer in, their name goes into the top bar, and a card over the bottom has rows as the
light's effects page has them: their state with Home Assistant's icon and since when, the battery where they report one,
and the changes of the last day, newest first, each with its time. A tap beside the markers, or the back key, goes back
to everyone. The screen gets where each marker is on the picture (pixels) and the card's words, never a place.

**A person's own tile** (any display, firmware 0.21.0) opens the same focused map with a tap, on a board that draws
pictures: where they are, with their card. Holding the tile opens its card with the history, as before; on a board
without pictures a tap opens the card too.

Markers stand exactly on their coordinates. Only markers that would cover each other on the glass fan out round their
middle, so each stays to be seen; the one a finger picked never moves.

## The choices

| Choice | What it does |
| --- | --- |
| **Follow** (map tile) | **Everyone**: every person, and every device tracker that is not already someone's, as Home Assistant's own map card does with `show_all`. **Chosen**: the list under it. |
| **On the map** / **Also on the map** | People and device trackers, up to eight. A device tracker is anything Home Assistant reports a place for: a phone through the Companion app, a car through its integration, a tag. One that only knows home or away has no place and is not offered. |
| **Show** (map tile) | **People and aircraft**, **People** only, or **Aircraft** only. With aircraft only, the map has no people and no zones, and its people's settings are hidden. |
| **Center on** | **Everyone**: the smallest view that holds everyone, with the zone each is in (not offered with aircraft only). **Around home**: your home zone in the middle. **Around this person** (a person's map): that person in the middle. **A place**: in one field, a latitude and longitude of your own in decimal degrees (as a map site copies them), or an airport's code: its ICAO, IATA or FAA code (KJFK, LAX, EGLL), and the field names the airport it found. Tessera keeps a list of the world's airports (from OurAirports), so nothing is looked up online. Without a place the map is around home. |
| **Distance** | How far Around home, Around this person and A place reach: street, neighborhood, town or region, or **Radius**: a circle of your own size round the middle, in kilometers or miles as Home Assistant counts (200 m to 500 km). With a radius, the map shows the circle a tenth larger across its short side and whatever fits along its long side, shades the circle (a little darker in the light look, a little lighter in the dark one) and draws its edge, and leaves out planes outside it (watched planes still show). Someone outside the view is a small marker at the edge, pointing the way. |
| **Markers** | **Photo**: a person's picture in their marker, as Home Assistant shows it, and their initials when they have none. **Initials**: always the letters. |
| **Names** | First names beside the markers: where the card has room (from about 200 pixels high, and always over the whole screen), always, or never. |
| **Zones** | Your zones as soft circles, or none. |
| **Streets** | The streets from Home Assistant's map, or a plain ground with only the zones and people: nothing is fetched. |
| **Look** | As the screen (light or dark with it), or always light, or always dark. |
| **Tap** (map tile) | **Full screen with keys**: the full view above; its name, back key and keys come with a tap on the map and go with the next tap, or by themselves five seconds after the last tap or key. A tap on a plane or person picks it either way. **Full screen, map only**: the map over the whole screen with nothing over it, and a tap anywhere closes it. **Nothing**: a tap does nothing. |
| **On the picture** | The tile's name on a small label at the bottom left, or nothing. |

## As Home Assistant does it

The map follows Home Assistant's own map card (`hui-map-card.ts`, `ha-map.ts` and `get_entity_location.ts` in its
frontend), so a household looks the same on a screen as in Home Assistant:

- **Where someone is**: their own latitude and longitude. A person without one who is in a zone (`in_zones`) stands in
  the middle of that zone.
- **Everyone** leaves out a tracker a person already follows (the person's `source`) and anything hidden in the entity
  registry.
- **Colours**: every person, tracker and zone gets a colour in the order Home Assistant made them (the home zone
  apart), so someone has the same colour on every map. The colours are the screen's own tile palette.
- **Markers**: a ring in that colour, around the person's picture (`entity_picture`) or the first letter of each word of
  their name, at most three. Where Home Assistant reports a GPS accuracy wider than the marker, a faint circle in the
  same colour shows it.
- **Zones**: passive zones are left out.

## Where the streets come from

Home Assistant Core has a `map_tiles` integration, which its own map card uses. It fetches OpenStreetMap's vector tiles
with Home Assistant's own identification, as the OpenStreetMap tile policy asks, and keeps them for a week. Tessera
asks Home Assistant for those tiles and never contacts a tile server itself. A request names a zoom and two whole numbers:
no entity, no name.

A vector tile says what is there (a street of some kind, water, a park) and nothing about how it looks, so Tessera
draws it in the screen's colours: a quiet ground of greys with white streets, water and green in soft tints, in light and
dark. The only strong colours on the card are the people and their zones. The card carries "© OpenStreetMap".

When Home Assistant has no tiles to give (an older Home Assistant, or no internet), the card is drawn from the zones and
the people alone, and Tessera asks again after ten minutes. A person's picture comes through Home Assistant too, or
from a public address on the internet; never from another address in the house.

## When it is drawn again

Never on a clock. With the layout, each map tile gets a short movement mark: a hash of who is on it and where (rounded to
about 25 meters, so a phone's drift is no change), their states, names, pictures and colours, the zones, and the tile's
own choices and name. The screen asks for a new picture when the mark changes. A household that stays put costs nothing.

When a picture does not come (firmware 0.30.0): a card keeps the map it shows until the next one has loaded, so
someone moving never empties it. If Tessera cannot draw one at that moment, the screen asks again after ten seconds
and then a little later each time, up to five minutes, and keeps the last map meanwhile. Older firmware asked once: a
page with only maps then showed its plain tiles until the page was turned.

## Light and dark

The screen says which look it is in when it asks for its pictures, and gets the map drawn for that look, unless the tile
keeps a look of its own. A screen in dark mode and one in light mode showing the same card each get their own picture.
Tessera keeps the last maps it drew by their mark, their size and their look, so a page that loads again for a camera
next to it does not draw its map again. The screen keeps its pictures under a name that includes the look as well, so
switching the look asks for the other map.

## Privacy

- **No location reaches a screen.** Who is on a card and how it frames them stay in Tessera; the screen gets the
  movement mark and pixels.
- **The picture travels unencrypted over your network**, on port 8098, like every other picture. A map shows roughly
  where someone is to anyone who can read that traffic. Keep that in mind for a screen on a guest network.
- A screen only gets a map for a map tile on its own saved layout, drawn from that saved tile.

## Aircraft

The map tile can show the planes around you. Under **Aircraft** in its settings, pick a sensor that lists flights:
the **Current in area** sensor of the [Flightradar24 integration](https://github.com/AlexandrErohin/home-assistant-flightradar24)
is one. Any sensor whose `flights` attribute is a list of aircraft with a `latitude` and a `longitude` works; `altitude`
(feet), `heading`, `ground_speed` (knots), `callsign`, `flight_number`, `aircraft_registration`, `aircraft_code`,
`on_ground` and the origin and destination codes are used where they are there.

The map stays the picture Tessera draws. The planes are not in it: the screen draws them over it and moves them in
place each time the sensor reports, so a plane moves without a new picture. Tessera sends the screen where each plane
stands on that picture, which way it flies and how far it goes in a minute, its label and its track, all in pixels.
No place reaches the screen, as with the people on the map.

| Choice | What it does |
| --- | --- |
| **Marker** | **Dot**, the smallest. **Dot and heading**: a short line the way it flies. **Plane**: a plane seen from above, turned to its heading. |
| **Label** | **Where there is room** (the callsign on a small card, with the altitude on a larger one and the full view), none, the callsign, the callsign and altitude, or also the speed, type and route. Labels keep clear of each other and of the planes, as a radar display keeps its data blocks apart, and lie under the full view's keys when those are up: a label with no room beside its plane moves out into open space, with a thin line back to it, and one with no room anywhere on the card is left out (a watched plane's always shows). A label keeps its place while its plane glides. |
| **Colour** | **By altitude**, from the ground up: grey on the ground, then orange, green, blue and purple (below 5,000, 15,000 and 30,000 ft, and above). Or the screen's accent for every plane. |
| **Between reports** | **Glide**: each plane flies on along its heading at its speed until the next report, for at most 30 seconds, so the map moves smoothly. **Hold**: each plane stays where the last report put it. |
| **Track** | The line a plane flew, for the number of seconds you choose (10 to 900). Tessera keeps each plane's places with their time itself, so a track works the same whatever the source keeps. |
| **On the ground** | Show or hide planes the source reports on the ground. |
| **Altitude** | Only planes between these altitudes, in feet. The Flightradar24 integration can filter by altitude too, which saves it requests; the tile's own range lets two maps show different heights. |
| **At most** | The planes closest to the middle of the map, up to 20. |
| **Watched** | Up to eight registrations or callsigns, such as N12345 or BAW432, each in a color of its own: red, orange, amber, green, blue or purple. A watched plane is always shown when it is on the map, whatever its altitude, on the ground or not and however many others there are. It is drawn larger, with a ring and its label, in its color and over the other planes. Dashes and case don't matter: G-EZAB and gezab are the same. |

Altitudes and speeds on the labels follow Home Assistant's unit system: feet and knots, or meters and kilometers per
hour.

**A plane's card.** On the full view, tap a plane to pick it: it gets a ring, the top bar takes its callsign, and a card
shows what the sensor knows of it, as many rows as the screen has room for: the airline and flight, the route, the
aircraft and its registration, its altitude (with an arrow for climbing or descending) and speed, and its squawk. The view
stays as it is, and the card follows the plane on every report; it goes to the top when the plane is under it. A tap
anywhere then lets it go and closes the card: on the map, on another plane, on the card itself, or the back key.

**How fresh it is.** A plane is as recent as the sensor's last report. Flightradar24 updates as often as its scan
interval in the integration's options, and it limits requests that come too often, so every 10 to 15 seconds is a
sensible pace. Glide fills the time in between.

**On the screen.** While a map card with aircraft is on the glass, or its full view is open, the screen asks Tessera for
its planes every 30 seconds and whenever another such card shows. Tessera answers at once and then sends the planes
again on each report of the sensor, for 75 seconds after the last ask. A screen that stops asking (another page, the
full view closed) gets nothing more. A screen with older firmware shows the map without planes.

## For developers

| Piece | Where |
| --- | --- |
| Reading Home Assistant's vector tiles | `screen_manager/app/vector_tiles.py` |
| The tiles through Home Assistant, cached | `screen_manager/app/map_tiles.py`, `HomeAssistant.map_tile` in `server.py` |
| Who is on it, framing, the movement mark, the drawing | `screen_manager/app/map_card.py` |
| Airports by their code, for a place of its own | `screen_manager/app/airports.py`, `airports.tsv.gz` written by `tools/build_airports.py`, `/api/airport` in `server.py` |
| A screen's request, the full view, focus and its card, pictures, kept maps | `Manager.answer_live`, `answer_map_full`, `map_sheet`, `map_render`, `map_photos` in `server.py` |
| The choices | `catalogue/person.yaml` (`map`), `core.validate_layout`, the map tile `screen.map` in `core.BUILTIN` |
| The firmware | `Tile::is_map()`, `card_art`, `live_wanted` (the mark and `dark`), the tap into `camera_open`, `MapSheet` and `map_sheet_draw` in `components/smart_display` |
| The editor | `TileInspector.vue`, `model/tile-options.ts`, `model/page-validation.ts` |
| Tests and renders | `tests/test_map_card.py`, `tools/render/map_tiles.py` |
| Aircraft: reading a source, choosing, labels, tracks, pixels and the message | `screen_manager/app/aircraft.py`, `catalogue/person.yaml` (`map.aircraft`) |
| Aircraft: a plane picked on the full view (`air:<id>`) and its card | `aircraft.card`, `picked_of`, `Manager.air_card` in `server.py`; `aircraft_plan::pick`, `map_pick_plane`, `air_full_card` in `runtime_tiles.h` |
| Aircraft: the screen's ask, its cards and every report | `Manager.answer_air`, `air_reports`, `air_message` in `server.py` |
| Aircraft on the screen | `aircraft_plan.h` (where a plane is, its outline, its label, labels kept apart with `place_labels`), `aircraft_view.cpp` (one object over the picture), `air_tick`, `air_receive` in `runtime_tiles.h`, op `air` in `page_receiver.cpp`, `theme.h` (`AIRCRAFT_*`, the watched colours from `ha::`) |
| What the map tile shows, its own place | `people_shown`, `centre_of`, `frame_view` in `map_card.py`; `aircraft.source_of` |
| Aircraft in the editor | `MapSection.vue`, `model/aircraft.ts` |
| Aircraft tests and renders | `tests/test_aircraft.py`, `tests/test_aircraft_plan.cpp`, `tools/render/aircraft.py` |

The picture pipeline the map shares is described in [CAMERA.md](CAMERA.md).
