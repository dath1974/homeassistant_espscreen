// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_aircraft_plan.cpp -o /tmp/test_aircraft_plan && /tmp/test_aircraft_plan
// Aircraft over a map (components/smart_display/aircraft_plan.h, docs/MAP.md "Aircraft"): where a plane is between two
// reports, the plane's outline turned to its heading, the arrow's tick, a label kept inside its card, labels kept apart
// with leader lines, whether a full view's planes belong to the picture on the glass, and a radar scope's light and beam.
#include "../components/smart_display/aircraft_plan.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>

using namespace aircraft_plan;

static bool near(float a, float b, float within = 0.01f) { return std::fabs(a - b) <= within; }

int main() {
  // A plane that glides goes on along its pixels a minute; one that holds stays; neither goes on past GLIDE_MS.
  Overlay o;
  o.at = 1000;
  Plane p;
  p.x = 100; p.y = 50; p.vx = 60; p.vy = -120;
  o.planes.push_back(p);
  Point at = aircraft_plan::at(o, p, 1000 + 15000);
  assert(near(at.x, 115) && near(at.y, 20));
  at = aircraft_plan::at(o, p, 1000 + 120000);
  assert(near(at.x, 130) && near(at.y, -10));
  at = aircraft_plan::at(o, p, 1000 + 15000, 2.0f, 0.5f);
  assert(near(at.x, 230) && near(at.y, 10));
  o.glide = false;
  at = aircraft_plan::at(o, p, 1000 + 15000);
  assert(near(at.x, 100) && near(at.y, 50));
  // The clock wraps: a report just before millis() turns over still glides forward.
  o.glide = true; o.at = 0xFFFFF000u;
  at = aircraft_plan::at(o, p, 0x00001000u);
  assert(near(at.x, 100 + 60 * 8192 / 60000.0f));

  // The outline's nose points along the heading: up for north, right for east, down for south.
  const Point c{50, 50};
  auto nose = [&](int heading) { return plane_shape(c, 20, heading)[0].p[0]; };
  assert(near(nose(0).x, 50) && near(nose(0).y, 40));
  assert(near(nose(90).x, 60, 0.05f) && near(nose(90).y, 50, 0.05f));
  assert(near(nose(180).x, 50, 0.05f) && near(nose(180).y, 60, 0.05f));
  // The wings span the plane's width across its heading, and every piece is rooted in the fuselage: a corner of each
  // triangle lies on it, so the outline is one solid piece (the tail joined to the body).
  float left = 1e9f, right = -1e9f;
  for (const auto &t : plane_shape(c, 20, 0)) {
    bool rooted = false;
    for (const auto &q : t.p) {
      left = std::min(left, q.x); right = std::max(right, q.x);
      rooted = rooted || (std::fabs(q.x - c.x) <= 0.07f * 20 + 0.01f && std::fabs(q.y - c.y) <= 10.01f);
    }
    assert(rooted);
  }
  assert(near(left, 40) && near(right, 60));
  // Every point stays within the plane's size of its middle, whatever the heading.
  for (int heading = 0; heading < 360; heading += 15)
    for (const auto &t : plane_shape(c, 20, heading))
      for (const auto &q : t.p) assert(std::hypot(q.x - c.x, q.y - c.y) <= 15.0f);

  // The arrow's tick starts at the dot's edge and points the way the plane flies.
  const auto east = heading_tick(c, 4, 6, 90);
  assert(near(east[0].x, 54) && near(east[1].x, 60) && near(east[0].y, 50) && near(east[1].y, 50));
  const auto north = heading_tick(c, 4, 6, 0);
  assert(near(north[1].y, 40) && near(north[1].x, 50));

  // A label stands right of its plane; on the right edge it goes left; it never leaves the frame.
  Box b = label_box({50, 50}, 5, 40, 20, 200, 100, 3);
  assert(b.x == 58 && b.y == 40);
  b = label_box({190, 50}, 5, 40, 20, 200, 100, 3);
  assert(b.x == 190 - 5 - 3 - 40);
  b = label_box({10, 2}, 5, 300, 20, 200, 100, 3);
  assert(b.x == 0 && b.y == 0);
  b = label_box({10, 99}, 5, 40, 20, 200, 100, 3);
  assert(b.y == 80);

  // Labels kept apart, as a radar display de-conflicts its data blocks.
  {
    auto label = [](float x, float y, bool watched = false) { Label l; l.c = {x, y}; l.reach = 4; l.w = 40; l.h = 16; l.watched = watched; return l; };
    auto apart = [](const std::vector<Placed> &placed) {
      for (size_t i = 0; i < placed.size(); ++i)
        for (size_t j = i + 1; j < placed.size(); ++j)
          if (placed[i].shown && placed[j].shown && overlaps(placed[i].box, placed[j].box)) return false;
      return true;
    };
    auto inside = [](const Box &b, int w, int h) { return b.x >= 0 && b.y >= 0 && b.x + b.w <= w && b.y + b.h <= h; };
    // Alone, a label stands where it always did: right of its plane, beside it, no leader.
    auto one = place_labels({label(50, 50)}, 300, 200, 3, 16);
    assert(one[0].spot == 0 && !one[0].leader && one[0].box.x == 57 && one[0].box.y == 42);
    // Two planes side by side: the second label goes elsewhere, clear of the first and of both markers.
    auto two = place_labels({label(100, 100), label(110, 102)}, 300, 200, 3, 16);
    assert(apart(two));
    for (const auto &p : two) {
      assert(!overlaps(p.box, {96, 96, 9, 9}) && !overlaps(p.box, {106, 98, 9, 9}));
    }
    // A crowd of twelve planes round one airport: every label clear of the others and inside the frame, the ones moved
    // off their plane with a leader.
    std::vector<Label> crowd;
    for (int n = 0; n < 12; ++n) crowd.push_back(label(150 + 6 * (n % 4), 100 + 6 * (n / 4)));
    auto placed = place_labels(crowd, 300, 200, 3, 16);
    assert(apart(placed));
    int leaders = 0;
    for (const auto &p : placed) { assert(p.shown && inside(p.box, 300, 200)); assert(p.spot != NO_SPOT); leaders += p.leader; }
    assert(leaders > 0);
    // A leader runs from the marker's edge to the label's box.
    for (size_t i = 0; i < placed.size(); ++i) {
      if (!placed[i].leader) continue;
      const auto ends = leader(crowd[i], placed[i].box);
      const float dx = ends[0].x - crowd[i].c.x, dy = ends[0].y - crowd[i].c.y;
      assert(near(std::sqrt(dx * dx + dy * dy), 4, 0.01f));
      const Box &b = placed[i].box;
      assert(ends[1].x >= b.x && ends[1].x <= b.x + b.w && ends[1].y >= b.y && ends[1].y <= b.y + b.h);
    }
    // A watched plane is placed first: listed last, it still takes the spot beside it.
    auto watched = place_labels({label(100, 100), label(104, 100, true)}, 300, 200, 3, 16);
    assert(watched[1].spot == 0 && watched[0].spot != 0);
    // Gliding a little, each label keeps the spot it had while that spot stays clear.
    std::vector<int> kept;
    for (const auto &p : placed) kept.push_back(p.spot);
    std::vector<Label> later = crowd;
    for (auto &l : later) { l.c.x += 1; l.c.y -= 1; }
    auto again = place_labels(later, 300, 200, 3, 16, kept);
    int same = 0;
    for (size_t i = 0; i < again.size(); ++i) same += again[i].spot == placed[i].spot;
    assert(apart(again) && same >= 10);
    // On the frame's right edge a lone label goes left; with no room at all it falls back inside the frame.
    auto edge = place_labels({label(290, 100)}, 300, 200, 3, 16);
    assert(edge[0].spot == 1 && inside(edge[0].box, 300, 200));
    Label huge = label(10, 10); huge.w = 400;
    assert(!place_labels({huge}, 300, 200, 3, 16)[0].shown);
    huge.watched = true;
    auto fallback = place_labels({huge}, 300, 200, 3, 16);
    assert(fallback[0].shown && fallback[0].spot == NO_SPOT && fallback[0].box.x == 0 && !fallback[0].leader);
    // A card too small for every label: the ones with no clear spot are left out, a watched one never.
    std::vector<Label> tight;
    for (int n = 0; n < 15; ++n) tight.push_back(label(60 + 3 * n, 40 + (n % 3), n == 14));
    auto few = place_labels(tight, 140, 80, 3, 16);
    int shown = 0;
    for (const auto &p : few) shown += p.shown;
    assert(apart(few) && shown < 15 && shown > 0 && few[14].shown);
  }

  // A label's lines, empty ones left out.
  const auto rows = lines("KLM123\n\n35000 ft");
  assert(rows.size() == 2 && rows[0] == "KLM123" && rows[1] == "35000 ft");
  assert(lines("").empty());

  // A full view's planes are shown only on the picture of the move and the focus they were placed for.
  Overlay full;
  full.move = "1,0.00,0.00"; full.focus = "";
  assert(fits_view(full, "1,0.00,0.00", ""));
  assert(!fits_view(full, "", ""));
  assert(!fits_view(full, "1,0.00,0.00", "person.someone"));

  // A plane picked (`air:<id>`) is the same view as nobody picked; a person picked is another.
  assert(picks_plane("air:abc") && picked_id("air:abc") == "abc" && !picks_plane("person.sam") && picked_id("person.sam").empty());
  Overlay seen;
  seen.move = ""; seen.focus = "";
  assert(fits_view(seen, "", "air:abc") && !fits_view(seen, "", "person.sam"));
  seen.focus = "air:old";
  assert(fits_view(seen, "", "") && fits_view(seen, "", "air:new"));
  // A finger picks the nearest plane with an id within its reach, where it is now, on the picture as shown.
  {
    Overlay full;
    full.at = 0; full.glide = false;
    Plane a; a.x = 100; a.y = 100; a.id = "a";
    Plane b; b.x = 120; b.y = 100; b.id = "b";
    Plane none; none.x = 300; none.y = 300;  // a card's plane: no id, never picked
    full.planes = {a, b, none};
    assert(pick(full, 104, 100, 16, 0) == "a");
    assert(pick(full, 117, 101, 16, 0) == "b");
    assert(pick(full, 160, 100, 16, 0).empty());
    assert(pick(full, 300, 300, 16, 0).empty());
    assert(pick(full, 208, 200, 16, 0, 2.0f, 2.0f) == "a");  // on a picture shown twice as large
  }

  // A radar scope (docs/MAP.md, "Radar"): low planes dim, high ones bright; no altitude is drawn as the ground's.
  for (int b = 1; b < BANDS; ++b) assert(band_light(b) > band_light(b - 1));
  assert(band_light(NO_BAND) == band_light(0) && band_light(2) == 1.0f && band_light(BANDS - 1) <= 2.0f);
  // The beam turns clockwise from north once in SWEEP_MS; bearings on the glass are from up, clockwise.
  assert(near(beam(0), 0) && near(beam(SWEEP_MS / 4), 90) && near(beam(SWEEP_MS + SWEEP_MS / 2), 180));
  const Point mid{100, 100};
  assert(near(bearing(mid, {100, 50}), 0) && near(bearing(mid, {150, 100}), 90) && near(bearing(mid, {100, 150}), 180) &&
         near(bearing(mid, {50, 100}), 270));
  // A plane lights up as the beam passes and fades after; one the beam is about to reach is dark.
  assert(near(behind(10, 350), 20) && near(behind(350, 10), 340));
  assert(near(afterglow(behind(90, 90)), 1) && afterglow(behind(120, 90)) > afterglow(behind(200, 90)) &&
         afterglow(behind(80, 90)) < 0.05f);
  // The box round a wedge holds its ends and every quarter it passes, and no more.
  {
    const Box east = wedge_box(mid, 50, 80, 100);  // round east: the middle, out to x 150
    assert(east.x <= 100 && east.x + east.w >= 150 && east.y <= 100 - 8 && east.y + east.h >= 100 + 8 && east.x >= 96);
    const Box north = wedge_box(mid, 50, 350, 10);  // across north, over the turn of 360
    assert(north.y <= 50 && north.y + north.h >= 100 && north.x <= 100 - 8 && north.x + north.w >= 100 + 8 && north.y + north.h <= 104);
    const Box half = wedge_box(mid, 50, 0, 180);  // east half
    assert(half.y <= 50 && half.y + half.h >= 150 && half.x + half.w >= 150 && half.x >= 96);
  }

  // The beam passes a bearing between two frames, across north too; a frame that did not move passes nothing.
  assert(crossed(80, 95, 90) && !crossed(80, 95, 100) && !crossed(80, 95, 70));
  assert(crossed(355, 5, 0) && crossed(355, 5, 359) && !crossed(355, 5, 10));
  assert(!crossed(90, 90, 90));
  {
    assert(holds({0, 0, 10, 10}, {2, 2, 8, 8}) && !holds({0, 0, 10, 10}, {2, 2, 9, 8}));
    const Box j = join({0, 0, 4, 4}, {10, 20, 5, 5});
    assert(j.x == 0 && j.y == 0 && j.w == 15 && j.h == 25);
  }

  std::puts("aircraft plan: ok");
  return 0;
}
