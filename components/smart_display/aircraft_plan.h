#pragma once
// Aircraft over a map tile (docs/MAP.md, "Aircraft"): the planes ESP Screen Manager sends for a map's picture (op "air",
// screen_manager/app/aircraft.py), and where each is drawn at a moment. This file only plans; aircraft_view.cpp paints a
// plan in one LVGL object over the picture, as the meter and the energy card do, so twenty planes with their tracks and
// labels are one object.
//
// The app places every plane on the picture it drew (pixels, never a place) and says how far it flies in a minute, in
// pixels of that picture. Between two reports a plane that glides goes on along its heading for at most GLIDE_MS, as a
// flight map does; one that holds stands still until the next report.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

namespace aircraft_plan {
enum Marker : uint8_t { DOT, ARROW, PLANE };
// Bands of altitude the app sends (aircraft.BANDS): on the ground, below 5,000 ft, below 15,000, below 30,000, above.
// NO_BAND: the source gave no altitude.
constexpr int BANDS = 5, NO_BAND = -1, NO_HEADING = -1;
// How long a plane glides on after its report: a source that stopped reporting leaves its planes where the last report
// and this much flight put them.
constexpr uint32_t GLIDE_MS = 30000;
// Watched aircraft (aircraft.WATCH_COLOURS): a plane's colour is 1 to WATCH_COLOURS, 0 for one nobody watches.
constexpr int WATCH_COLOURS = 6;
// A watched plane is drawn this much larger, with a ring around it.
constexpr float WATCH_SCALE = 1.35f;
// The app's 20 nearest and the watched ones beside them (catalogue/person.yaml map.watch max).
constexpr size_t MOST_PLANES = 28, MOST_TRACK = 24;

struct Plane {
  int x = 0, y = 0;            // on the picture the app drew, `width` x `height`
  int heading = NO_HEADING;    // degrees from north, clockwise
  int band = NO_BAND;
  int vx = 0, vy = 0;          // pixels a minute
  std::string label;           // its lines, joined by '\n'
  std::vector<int16_t> track;  // x, y, x, y ... oldest first, ending where the plane is
  int watch = 0;               // 1 to WATCH_COLOURS for a watched plane, in its colour
};

struct Overlay {
  bool full = false;  // the full view of tile `index`, else the card of tile `index` on the page
  int index = -1;
  int width = 0, height = 0;  // the picture the planes are placed on
  Marker marker = DOT;
  bool by_altitude = true;  // coloured by band, else in the screen's accent
  bool glide = true;
  std::string move, focus;  // a full view's: the move of its keys and the one picked it was placed for
  uint32_t at = 0;          // millis() when it came
  std::vector<Plane> planes;
};

struct Point { float x, y; };

// How far `o`'s report is behind `now`, as far as a plane glides.
inline uint32_t since(const Overlay &o, uint32_t now) {
  if (!o.glide) return 0;
  return std::min<uint32_t>(now - o.at, GLIDE_MS);
}
// Where a plane is at `now`, on a picture shown at `sx`, `sy` of the size the app drew it.
inline Point at(const Overlay &o, const Plane &p, uint32_t now, float sx = 1, float sy = 1) {
  const float minutes = since(o, now) / 60000.0f;
  return {(p.x + p.vx * minutes) * sx, (p.y + p.vy * minutes) * sy};
}

// The triangles of a plane seen from above, `size` pixels nose to tail, turned to `heading`: the fuselage, the two
// wings and the tail, so it reads as a plane even a few millimetres across.
struct Triangle { std::array<Point, 3> p; };
inline std::array<Triangle, 4> plane_shape(Point c, float size, int heading) {
  const float a = (heading < 0 ? 0 : heading) * 3.14159265f / 180.0f, s = std::sin(a), k = std::cos(a);
  const float h = size / 2;
  // In the plane's own frame (x right, y forward), then turned: forward is north at heading 0, up on the glass.
  auto turn = [&](float x, float y) { return Point{c.x + x * k + y * s, c.y + x * s - y * k}; };
  return {{
      {{turn(0, h), turn(-0.13f * size, -0.40f * h), turn(0.13f * size, -0.40f * h)}},                 // nose to body
      {{turn(0, 0.25f * h), turn(-0.5f * size, -0.15f * h), turn(0.5f * size, -0.15f * h)}},          // wings
      {{turn(0, -0.30f * h), turn(-0.06f * size, -h), turn(0.06f * size, -h)}},                        // tail boom
      {{turn(0, -0.70f * h), turn(-0.22f * size, -h), turn(0.22f * size, -h)}},                        // tailplane
  }};
}
// The short line an arrow marker points along: from the dot's edge out by `length`, toward `heading`.
inline std::array<Point, 2> heading_tick(Point c, float radius, float length, int heading) {
  const float a = heading * 3.14159265f / 180.0f, s = std::sin(a), k = -std::cos(a);
  return {{{c.x + s * radius, c.y + k * radius}, {c.x + s * (radius + length), c.y + k * (radius + length)}}};
}

struct Box { int x, y, w, h; };
// A label's place beside its plane: to the right of the marker, its middle on the plane's height; to the left where the
// right has no room; and kept inside the frame.
inline Box label_box(Point c, int reach, int w, int h, int frame_w, int frame_h, int gap) {
  int x = (int) std::lround(c.x) + reach + gap;
  if (x + w > frame_w) x = (int) std::lround(c.x) - reach - gap - w;
  int y = (int) std::lround(c.y) - h / 2;
  x = std::max(0, std::min(x, frame_w - w));
  y = std::max(0, std::min(y, frame_h - h));
  return {x, y, w, h};
}

// The lines of a label.
inline std::vector<std::string> lines(const std::string &label) {
  std::vector<std::string> out;
  size_t start = 0;
  while (start <= label.size()) {
    const size_t end = label.find('\n', start);
    const std::string line = label.substr(start, end == std::string::npos ? std::string::npos : end - start);
    if (!line.empty()) out.push_back(line);
    if (end == std::string::npos) break;
    start = end + 1;
  }
  return out;
}

// Whether a full view's overlay belongs to the picture on the glass: placed for the move its keys show and the one picked.
inline bool fits_view(const Overlay &o, const std::string &move_shown, const std::string &focus) {
  return o.move == move_shown && o.focus == focus;
}
}  // namespace aircraft_plan
