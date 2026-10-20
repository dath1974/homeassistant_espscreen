// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_aircraft_plan.cpp -o /tmp/test_aircraft_plan && /tmp/test_aircraft_plan
// Aircraft over a map (components/smart_display/aircraft_plan.h, docs/MAP.md "Aircraft"): where a plane is between two
// reports, the plane's outline turned to its heading, the arrow's tick, a label kept inside its card, and whether a full
// view's planes belong to the picture on the glass.
#include "../components/smart_display/aircraft_plan.h"
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
  // The wings span the plane's width across its heading.
  const auto wings = plane_shape(c, 20, 0)[1];
  assert(near(wings.p[1].x, 40) && near(wings.p[2].x, 60));
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

  std::puts("aircraft plan: ok");
  return 0;
}
