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

// Labels kept apart, as a radar display de-conflicts its data blocks: each label takes the first spot round its plane
// that is inside the frame and clear of every label placed before it and of every plane's marker, and one moved off its
// plane is drawn with a leader line back to it. The spots, in order: beside the plane (right, left), its corners, above
// and below, then the same eight directions on rings `step` further out (LABEL_RINGS of them). Watched planes are
// placed first, then the rest in the app's order. A label with no clear spot is left out (`shown` false), as a pile of
// text helps nobody on a small card and the full view has room for it; a watched plane's takes the spot it overlaps
// least instead, so its label always shows. A label keeps the spot it had (`kept`) while that spot stays clear, so labels hold still while their
// planes glide. `blocked`: what lies over the planes on the glass (a full view's keys), kept clear the same way.
constexpr int LABEL_DIRECTIONS = 8, LABEL_RINGS = 6, LABEL_SPOTS = LABEL_DIRECTIONS * (LABEL_RINGS + 1), NO_SPOT = -1;

struct Label {
  Point c;          // the plane, on the frame
  int reach = 0;    // from its middle to its marker's edge
  int w = 0, h = 0;
  bool watched = false;
};
struct Placed {
  Box box{0, 0, 0, 0};
  int spot = NO_SPOT;
  bool leader = false;
  bool shown = false;
};

inline bool overlaps(const Box &a, const Box &b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}
inline long overlap_area(const Box &a, const Box &b) {
  const int w = std::min(a.x + a.w, b.x + b.w) - std::max(a.x, b.x), h = std::min(a.y + a.h, b.y + b.h) - std::max(a.y, b.y);
  return w > 0 && h > 0 ? (long) w * h : 0;
}
// Spot `spot` of a label: direction spot % 8 (right, left, up-right, down-right, up-left, down-left, up, down), its near
// edge or corner `reach + gap + ring * step` from the plane.
inline Box spot_box(const Label &l, int spot, int gap, int step) {
  const int ring = spot / LABEL_DIRECTIONS, dir = spot % LABEL_DIRECTIONS;
  const int cx = (int) std::lround(l.c.x), cy = (int) std::lround(l.c.y);
  const int d = l.reach + gap + ring * step, k = (int) std::lround(d * 0.7071f);
  switch (dir) {
    case 0: return {cx + d, cy - l.h / 2, l.w, l.h};
    case 1: return {cx - d - l.w, cy - l.h / 2, l.w, l.h};
    case 2: return {cx + k, cy - k - l.h, l.w, l.h};
    case 3: return {cx + k, cy + k, l.w, l.h};
    case 4: return {cx - k - l.w, cy - k - l.h, l.w, l.h};
    case 5: return {cx - k - l.w, cy + k, l.w, l.h};
    case 6: return {cx - l.w / 2, cy - d - l.h, l.w, l.h};
    default: return {cx - l.w / 2, cy + d, l.w, l.h};
  }
}

inline std::vector<Placed> place_labels(const std::vector<Label> &labels, int frame_w, int frame_h, int gap, int step,
                                        const std::vector<int> &kept = {}, const std::vector<Box> &blocked = {}) {
  std::vector<Placed> out(labels.size());
  std::vector<Box> markers;
  markers.reserve(labels.size());
  for (const auto &l : labels) {
    const int cx = (int) std::lround(l.c.x), cy = (int) std::lround(l.c.y);
    markers.push_back({cx - l.reach, cy - l.reach, 2 * l.reach + 1, 2 * l.reach + 1});
  }
  std::vector<size_t> order;
  order.reserve(labels.size());
  for (size_t i = 0; i < labels.size(); ++i) if (labels[i].watched) order.push_back(i);
  for (size_t i = 0; i < labels.size(); ++i) if (!labels[i].watched) order.push_back(i);
  std::vector<Box> placed;
  placed.reserve(labels.size());
  for (const size_t i : order) {
    const Label &l = labels[i];
    if (l.w <= 0 || l.h <= 0) continue;
    auto inside = [&](const Box &b) { return b.x >= 0 && b.y >= 0 && b.x + b.w <= frame_w && b.y + b.h <= frame_h; };
    auto cost = [&](const Box &b) {
      long sum = 0;
      for (const auto &p : placed) sum += overlap_area(b, p);
      for (const auto &k : blocked) sum += overlap_area(b, k);
      for (size_t m = 0; m < markers.size(); ++m) if (m != i) sum += overlap_area(b, markers[m]);
      return sum;
    };
    int best = NO_SPOT;
    long best_cost = -1;
    auto consider = [&](int spot) {
      const Box b = spot_box(l, spot, gap, step);
      if (!inside(b)) return false;
      const long c = cost(b);
      if (best == NO_SPOT || c < best_cost) { best = spot; best_cost = c; }
      return c == 0;
    };
    bool clear = i < kept.size() && kept[i] >= 0 && kept[i] < LABEL_SPOTS && consider(kept[i]);
    for (int spot = 0; !clear && spot < LABEL_SPOTS; ++spot) clear = consider(spot);
    Placed &p = out[i];
    if (!clear && !l.watched) continue;
    p.shown = true;
    if (best == NO_SPOT) {
      // Larger than every spot the frame has room for: beside its plane, kept inside the frame as before.
      p.box = label_box(l.c, l.reach, l.w, l.h, frame_w, frame_h, gap);
    } else {
      p.box = spot_box(l, best, gap, step);
      p.spot = best;
      p.leader = best >= LABEL_DIRECTIONS;
    }
    placed.push_back(p.box);
  }
  return out;
}
// A leader line from a plane's marker to its label moved away: from the marker's edge toward the nearest point of the
// box, ending on the box.
inline std::array<Point, 2> leader(const Label &l, const Box &b) {
  const Point near{std::max<float>(b.x, std::min<float>(l.c.x, b.x + b.w - 1)), std::max<float>(b.y, std::min<float>(l.c.y, b.y + b.h - 1))};
  const float dx = near.x - l.c.x, dy = near.y - l.c.y, d = std::sqrt(dx * dx + dy * dy);
  if (d <= l.reach) return {{near, near}};
  return {{{l.c.x + dx / d * l.reach, l.c.y + dy / d * l.reach}, near}};
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
