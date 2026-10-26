// Aircraft over a map's picture on the glass (docs/MAP.md, "Aircraft"): aircraft_plan.h's planes painted in one object
// over the picture, in its draw event, so twenty planes with their tracks and labels cost one object and one redraw.
//
// Compiled on its own, as meter_view.cpp is: every header of this component lands in main.cpp, and on Xtensa the
// literal pool of one object file must stay within reach of all of its code (page_receiver.cpp says how that broke).
#include "aircraft_view.h"
#include "runtime_tiles.h"

#include <algorithm>
#include <cmath>

namespace aircraft_view {
namespace rt = runtime_tiles;
namespace ap = aircraft_plan;

struct View {
  lv_obj_t *layer = nullptr;
  ap::Overlay overlay;
  float sx = 1, sy = 1;  // the picture on the glass against the one the planes were placed on
  bool hidden = false;
  std::vector<int> spots;  // where each label stood the last time, kept while it stays clear (aircraft_plan.h)
  std::string picked;      // the plane a finger picked on a full view, ringed
  lv_timer_t *sweeping = nullptr;  // a radar scope's beam turning, every ap::SWEEP_FRAME_MS
  float beam_drawn = -1;           // the bearing it was drawn at last
};

// ---- A radar scope (docs/MAP.md, "Radar"): one phosphor (theme.h radar::TINTS) from its ground to its hottest light.
static const theme::radar::Tint &tint_of(const ap::Overlay &o) {
  return theme::radar::TINTS[o.radar.tint >= 0 && o.radar.tint < theme::radar::TINT_COUNT ? o.radar.tint : 0];
}
// `light` 0 is the ground, 1 the glow, 2 the hottest light (ap::BAND_LIGHT).
static lv_color_t phosphor(const ap::Overlay &o, float light) {
  const auto &t = tint_of(o);
  light = std::max(0.0f, std::min(2.0f, light));
  if (light <= 1) return lv_color_hex(theme::mix(t.glow, t.ground, (uint8_t) std::lround(light * 255)));
  return lv_color_hex(theme::mix(t.hot, t.glow, (uint8_t) std::lround((light - 1) * 255)));
}

// A plane's colour: a watched plane's own (Home Assistant's colours, in the order of aircraft.WATCH_COLOURS), else its
// band of altitude in the flight map's rainbow, or the screen's accent.
static lv_color_t colour_of(const ap::Overlay &o, const ap::Plane &p) {
  static constexpr theme::Role BANDS[ap::BANDS] = {theme::AIRCRAFT_GROUND, theme::AIRCRAFT_LOW, theme::AIRCRAFT_MID,
                                                   theme::AIRCRAFT_HIGH, theme::AIRCRAFT_TOP};
  static constexpr uint32_t WATCH[ap::WATCH_COLOURS] = {theme::ha::RED, theme::ha::ORANGE, theme::ha::AMBER,
                                                        theme::ha::GREEN, theme::ha::BLUE, theme::ha::PURPLE};
  if (p.watch > 0 && p.watch <= ap::WATCH_COLOURS) return lv_color_hex(WATCH[p.watch - 1]);
  // On a scope: its phosphor, dim low down and bright up high, or the glow alone.
  if (o.radar.on) return phosphor(o, o.by_altitude ? ap::band_light(p.band) : 1.0f);
  if (!o.by_altitude) return theme::color(theme::ACCENT);
  return theme::color(p.band >= 0 && p.band < ap::BANDS ? BANDS[p.band] : theme::AIRCRAFT_GROUND);
}

// The sizes of the reference look, larger on a full view, which is seen from further away.
struct Sizes { int dot, plane, tick, line, halo, pad, gap, radius; };
static Sizes sizes(bool full) {
  return {ui::px(full ? 12 : 8), ui::px(full ? 24 : 16), ui::px(full ? 9 : 6), std::max(1, ui::px(2)),
          std::max(1, ui::px(2)), ui::px(3), ui::px(4), ui::px(4)};
}

// LVGL's precise points are whole numbers or floats by its configuration.
static lv_point_precise_t precise(ap::Point p) {
  return {static_cast<lv_value_precise_t>(std::lround(p.x)), static_cast<lv_value_precise_t>(std::lround(p.y))};
}
// Rounded ends only where a line ends: segments of one track that overlap there would show darker dots at their joints.
static void line(lv_layer_t *layer, ap::Point a, ap::Point b, lv_color_t colour, int width, lv_opa_t opa, bool round_start = true,
                 bool round_end = true) {
  lv_draw_line_dsc_t dsc;
  lv_draw_line_dsc_init(&dsc);
  dsc.color = colour; dsc.width = width; dsc.opa = opa; dsc.round_start = round_start; dsc.round_end = round_end;
  dsc.p1 = precise(a); dsc.p2 = precise(b);
  lv_draw_line(layer, &dsc);
}
// A circle's outline alone: the ring around a watched plane.
static void ring(lv_layer_t *layer, ap::Point c, int d, int width, lv_color_t colour) {
  lv_draw_rect_dsc_t dsc;
  lv_draw_rect_dsc_init(&dsc);
  dsc.radius = LV_RADIUS_CIRCLE; dsc.bg_opa = LV_OPA_TRANSP;
  dsc.border_width = width; dsc.border_color = colour; dsc.border_opa = LV_OPA_COVER;
  const int x = (int) std::lround(c.x) - d / 2, y = (int) std::lround(c.y) - d / 2;
  lv_area_t box{x, y, x + d - 1, y + d - 1};
  lv_draw_rect(layer, &dsc, &box);
}
static void dot(lv_layer_t *layer, ap::Point c, int d, lv_color_t fill, int border, lv_color_t edge, lv_opa_t opa = LV_OPA_COVER) {
  lv_draw_rect_dsc_t dsc;
  lv_draw_rect_dsc_init(&dsc);
  dsc.radius = LV_RADIUS_CIRCLE; dsc.bg_color = fill; dsc.bg_opa = opa;
  dsc.border_width = border; dsc.border_color = edge; dsc.border_opa = border ? LV_OPA_COVER : LV_OPA_TRANSP;
  const int x = (int) std::lround(c.x) - d / 2, y = (int) std::lround(c.y) - d / 2;
  lv_area_t box{x, y, x + d - 1, y + d - 1};
  lv_draw_rect(layer, &dsc, &box);
}
static void shape(lv_layer_t *layer, ap::Point c, float size, int heading, lv_color_t colour, lv_opa_t opa) {
  for (const auto &t : ap::plane_shape(c, size, heading)) {
    lv_draw_triangle_dsc_t dsc;
    lv_draw_triangle_dsc_init(&dsc);
    dsc.color = colour; dsc.opa = opa;
    for (int n = 0; n < 3; ++n) dsc.p[n] = precise(t.p[n]);
    lv_draw_triangle(layer, &dsc);
  }
}

static void triangle(lv_layer_t *layer, ap::Point a, ap::Point b, ap::Point c, lv_color_t colour, lv_opa_t opa) {
  lv_draw_triangle_dsc_t dsc;
  lv_draw_triangle_dsc_init(&dsc);
  dsc.color = colour; dsc.opa = opa;
  dsc.p[0] = precise(a); dsc.p[1] = precise(b); dsc.p[2] = precise(c);
  lv_draw_triangle(layer, &dsc);
}

// The middle of a scope on the glass, and how far its farthest corner is.
static ap::Point scope_middle(const View *view, const lv_area_t &a) {
  return {a.x1 + view->overlay.radar.x * view->sx, a.y1 + view->overlay.radar.y * view->sy};
}
static float scope_reach(ap::Point c, const lv_area_t &a) {
  float far = 0;
  for (const float x : {(float) a.x1, (float) a.x2}) for (const float y : {(float) a.y1, (float) a.y2})
    far = std::max(far, std::hypot(x - c.x, y - c.y));
  return far + 2;
}
// The beam and its afterglow, a fan of slices fading behind it, under every plane.
static constexpr int TRAIL_SLICES = 3;
// Each slice is drawn in pieces SEGMENT_PX long from the middle out: LVGL works out a triangle over the whole box round
// it, and the box of one long thin slice across a diagonal is most of a quarter of the glass.
static constexpr float SEGMENT_PX = 40.0f;
static void draw_beam(lv_layer_t *layer, const ap::Overlay &o, ap::Point c, float reach, float beam, int width) {
  auto at = [&](float b, float r) {
    const float a = b * 3.14159265f / 180.0f;
    return ap::Point{c.x + std::sin(a) * r, c.y - std::cos(a) * r};
  };
  const lv_color_t glow = phosphor(o, 1.0f);
  const int pieces = std::max(1, (int) std::ceil(reach / SEGMENT_PX));
  for (int k = 0; k < TRAIL_SLICES; ++k) {
    const float to = beam - ap::SWEEP_TRAIL * k / TRAIL_SLICES, from = beam - ap::SWEEP_TRAIL * (k + 1) / TRAIL_SLICES;
    const lv_opa_t opa = (lv_opa_t) (110 * (TRAIL_SLICES - k) / TRAIL_SLICES);
    triangle(layer, c, at(from, reach / pieces), at(to, reach / pieces), glow, opa);
    for (int n = 1; n < pieces; ++n) {
      const float r0 = reach * n / pieces, r1 = reach * (n + 1) / pieces;
      triangle(layer, at(from, r0), at(to, r0), at(to, r1), glow, opa);
      triangle(layer, at(from, r0), at(to, r1), at(from, r1), glow, opa);
    }
  }
  line(layer, c, at(beam, reach), phosphor(o, 1.6f), width, LV_OPA_COVER);
}
// How lit a plane is by the beam, in steps, so a plane is drawn again only when it changes a step.
static constexpr int GLOW_STEPS = 6;
static int glow_step(const View *view, ap::Point c, ap::Point plane, float beam) {
  if (!view->overlay.radar.sweep) return 0;
  return (int) std::lround(ap::afterglow(ap::behind(beam, ap::bearing(c, plane))) * GLOW_STEPS);
}

static void draw(lv_event_t *e) {
  auto *view = static_cast<View *>(lv_event_get_user_data(e));
  if (!view || view->hidden) return;
  lv_layer_t *layer = lv_event_get_layer(e);
  lv_area_t a;
  lv_obj_get_coords(lv_event_get_target_obj(e), &a);
  const ap::Overlay &o = view->overlay;
  const Sizes s = sizes(o.full);
  const uint32_t now = lv_tick_get();
  const bool radar = o.radar.on;
  // On a scope the halo is its ground, so every mark reads as lit phosphor on the dark tube.
  const lv_color_t halo = radar ? lv_color_hex(tint_of(o).ground) : theme::color(theme::CARD);
  const ap::Point middle = radar ? scope_middle(view, a) : ap::Point{0, 0};
  const float beam = radar && o.radar.sweep ? ap::beam(now) : 0;
  if (radar && o.radar.sweep) {
    draw_beam(layer, o, middle, scope_reach(middle, a), beam, std::max(2, s.line * 3 / 2));
    view->beam_drawn = beam;
  }
  auto on_glass = [&](float x, float y) { return ap::Point{a.x1 + x * view->sx, a.y1 + y * view->sy}; };
  std::vector<ap::Point> places;
  places.reserve(o.planes.size());
  for (const auto &p : o.planes) {
    const ap::Point at = ap::at(o, p, now, view->sx, view->sy);
    places.push_back({a.x1 + at.x, a.y1 + at.y});
  }
  // The tracks first, under every marker: from the oldest place to where the plane is now. On a scope its history,
  // a dot at each place it was, the older ones fainter, as a radar keeps a plane's last returns.
  for (size_t i = 0; i < o.planes.size(); ++i) {
    const auto &track = o.planes[i].track;
    if (track.size() < 4) continue;
    const lv_color_t colour = colour_of(o, o.planes[i]);
    const size_t points = track.size() / 2;
    if (radar) {
      const int d = std::max(2, s.line + 1);
      for (size_t n = 0; n + 1 < points; ++n)
        dot(layer, on_glass(track[2 * n], track[2 * n + 1]), d, colour, 0, colour, (lv_opa_t) (60 + 140 * (n + 1) / points));
      continue;
    }
    for (size_t n = 0; n + 1 < points; ++n) {
      const ap::Point from = on_glass(track[2 * n], track[2 * n + 1]);
      const ap::Point to = n + 2 == points ? places[i] : on_glass(track[2 * n + 2], track[2 * n + 3]);
      line(layer, from, to, colour, s.line, LV_OPA_70, n == 0, n + 2 == points);
    }
  }
  // The app sends the watched planes last, so they lie over the others.
  for (size_t i = 0; i < o.planes.size(); ++i) {
    const auto &p = o.planes[i];
    lv_color_t colour = colour_of(o, p);
    const ap::Point c = places[i];
    const float grow = p.watch ? ap::WATCH_SCALE : 1.0f;
    const int d = (int) std::lround(s.dot * grow), size = (int) std::lround(s.plane * grow);
    if (radar) {
      // A blip: a soft glow round it, brighter as the beam passes and fading after.
      const int step = glow_step(view, middle, c, beam);
      const float flare = (float) step / GLOW_STEPS;
      if (step && !p.watch) colour = phosphor(o, ap::band_light(o.by_altitude ? p.band : 2) + 0.7f * flare);
      const int across = (o.marker == ap::PLANE ? size : d) * 8 / 5;
      dot(layer, c, across, colour, 0, colour, (lv_opa_t) (28 + 72 * flare));
    }
    if (!view->picked.empty() && p.id == view->picked) {
      // The plane picked: a wide ring in the ink round a halo of the card's colour, outside a watched plane's own.
      const int across = (o.marker == ap::PLANE && p.heading != ap::NO_HEADING ? size : d) + 8 * s.halo + 4 * s.line;
      ring(layer, c, across + 2 * s.halo, 2 * s.line + 2 * s.halo, halo);
      ring(layer, c, across, 2 * s.line, radar ? phosphor(o, 2.0f) : theme::color(theme::INK));
    }
    if (p.watch) {
      // A ring in its colour round a halo of the card's, a little beyond the marker.
      const int across = (o.marker == ap::PLANE && p.heading != ap::NO_HEADING ? size : d) + 4 * s.halo + 2 * s.line;
      ring(layer, c, across + 2 * s.halo, s.line + 2 * s.halo, halo);
      ring(layer, c, across, s.line, colour);
    }
    if (o.marker == ap::PLANE && p.heading != ap::NO_HEADING) {
      // A halo in the card's colour, so the plane reads on streets and on water alike.
      shape(layer, c, size + 2 * s.halo, p.heading, halo, LV_OPA_80);
      shape(layer, c, size, p.heading, colour, LV_OPA_COVER);
      continue;
    }
    if (radar && o.marker == ap::ARROW && (p.vx || p.vy)) {
      // A scope's vector: where the plane will be in a minute, as a controller's scope draws it.
      const ap::Point ahead{c.x + p.vx * view->sx, c.y + p.vy * view->sy};
      line(layer, c, ahead, colour, s.line, LV_OPA_80);
    } else if (o.marker == ap::ARROW && p.heading != ap::NO_HEADING) {
      const auto tick = ap::heading_tick(c, d / 2.0f, s.tick * grow, p.heading);
      line(layer, tick[0], tick[1], halo, s.line + 2 * s.halo, LV_OPA_80);
      line(layer, tick[0], tick[1], colour, s.line, LV_OPA_COVER);
    }
    dot(layer, c, d, colour, radar ? 0 : s.halo, halo);
  }
  // The labels last, over everything: a soft pill of the card's colour with the plane's lines in ink, kept apart from each
  // other and from the markers, with a leader line to a label moved off its plane (aircraft_plan.h place_labels).
  const lv_font_t *font = o.full && rt::label_font ? rt::label_font : rt::small_font ? rt::small_font : rt::label_font;
  if (!font) return;
  const int line_h = lv_font_get_line_height(font);
  const int frame_w = lv_area_get_width(&a), frame_h = lv_area_get_height(&a);
  std::vector<std::vector<std::string>> rows(o.planes.size());
  std::vector<ap::Label> labels(o.planes.size());
  for (size_t i = 0; i < o.planes.size(); ++i) {
    const bool watched = o.planes[i].watch != 0;
    ap::Label &l = labels[i];
    l.c = {places[i].x - a.x1, places[i].y - a.y1};
    l.reach = (int) std::lround((o.marker == ap::PLANE ? s.plane : s.dot) * (watched ? ap::WATCH_SCALE : 1.0f) / 2) +
              (watched ? 2 * s.halo + s.line : 0);
    l.watched = watched;
    rows[i] = ap::lines(o.planes[i].label);
    if (rows[i].empty()) continue;
    int w = 0;
    for (const auto &row : rows[i]) w = std::max(w, rt::text_width(row, font));
    l.w = w + 2 * s.pad;
    l.h = (int) rows[i].size() * line_h + s.pad;
  }
  // What lies over the planes (a full view's keys, its back key and name): the shown siblings above this layer, save one
  // as large as half the picture, which would block every spot alike.
  std::vector<ap::Box> blocked;
  lv_obj_t *self = lv_event_get_target_obj(e), *parent = lv_obj_get_parent(self);
  const int32_t own = lv_obj_get_index(self), count = parent ? (int32_t) lv_obj_get_child_count(parent) : 0;
  for (int32_t n = own + 1; n < count; ++n) {
    lv_obj_t *above = lv_obj_get_child(parent, n);
    if (!above || lv_obj_has_flag(above, LV_OBJ_FLAG_HIDDEN)) continue;
    lv_area_t k;
    lv_obj_get_coords(above, &k);
    const ap::Box box{k.x1 - a.x1, k.y1 - a.y1, lv_area_get_width(&k), lv_area_get_height(&k)};
    if ((long) box.w * box.h * 2 >= (long) frame_w * frame_h) continue;
    if (box.x + box.w <= 0 || box.y + box.h <= 0 || box.x >= frame_w || box.y >= frame_h) continue;
    blocked.push_back(box);
  }
  const std::vector<ap::Placed> placed = ap::place_labels(labels, frame_w, frame_h, s.gap, line_h, view->spots, blocked);
  view->spots.assign(placed.size(), ap::NO_SPOT);
  for (size_t i = 0; i < placed.size(); ++i) view->spots[i] = placed[i].spot;
  // The leaders under every label: a halo of the card's colour, then the plane's own.
  for (size_t i = 0; i < placed.size(); ++i) {
    if (!placed[i].shown || !placed[i].leader) continue;
    const auto ends = ap::leader(labels[i], placed[i].box);
    const ap::Point from{a.x1 + ends[0].x, a.y1 + ends[0].y}, to{a.x1 + ends[1].x, a.y1 + ends[1].y};
    line(layer, from, to, halo, s.line + 2 * s.halo, LV_OPA_80);
    line(layer, from, to, colour_of(o, o.planes[i]), std::max(1, s.line / 2), LV_OPA_COVER);
  }
  for (size_t i = 0; i < placed.size(); ++i) {
    if (!placed[i].shown) continue;
    const ap::Box &box = placed[i].box;
    lv_draw_rect_dsc_t bg;
    lv_draw_rect_dsc_init(&bg);
    // On a scope a data block: square, the tube showing through, its text in the plane's own phosphor.
    bg.radius = radar ? 0 : s.radius; bg.bg_color = halo; bg.bg_opa = radar ? LV_OPA_60 : LV_OPA_80;
    // A watched plane's label is edged in its colour.
    if (labels[i].watched) { bg.border_width = s.line; bg.border_color = colour_of(o, o.planes[i]); bg.border_opa = LV_OPA_COVER; }
    lv_area_t area{a.x1 + box.x, a.y1 + box.y, a.x1 + box.x + box.w - 1, a.y1 + box.y + box.h - 1};
    lv_draw_rect(layer, &bg, &area);
    for (size_t n = 0; n < rows[i].size(); ++n) {
      lv_draw_label_dsc_t dsc;
      lv_draw_label_dsc_init(&dsc);
      dsc.font = font; dsc.text = rows[i][n].c_str();
      dsc.color = radar ? (n ? phosphor(o, 0.65f) : colour_of(o, o.planes[i])) : theme::color(n ? theme::MUTED : theme::INK);
      dsc.text_local = 1;
      const int y = area.y1 + s.pad / 2 + (int) n * line_h;
      lv_area_t text{area.x1 + s.pad, y, area.x2 - s.pad, y + line_h - 1};
      lv_draw_label(layer, &dsc, &text);
    }
  }
}

// A scope's beam turning: what it swept since the last frame and the planes whose light changed a step are drawn
// again, not the whole picture.
static void sweep(lv_timer_t *timer) {
  auto *view = static_cast<View *>(lv_timer_get_user_data(timer));
  if (!view || !view->layer || view->hidden || lv_obj_has_flag(view->layer, LV_OBJ_FLAG_HIDDEN)) return;
  lv_area_t a;
  lv_obj_get_coords(view->layer, &a);
  const ap::Overlay &o = view->overlay;
  const ap::Point c = scope_middle(view, a);
  const uint32_t now = lv_tick_get();
  const float was = view->beam_drawn < 0 ? ap::beam(now) : view->beam_drawn, beam = ap::beam(now);
  const ap::Box box = ap::wedge_box(c, scope_reach(c, a), was - ap::SWEEP_TRAIL - 2, beam + 2);
  lv_area_t area{box.x, box.y, box.x + box.w - 1, box.y + box.h - 1};
  lv_obj_invalidate_area(view->layer, &area);
  const int reach = sizes(o.full).plane * 2;
  for (const auto &p : o.planes) {
    const ap::Point at = ap::at(o, p, now, view->sx, view->sy), plane{a.x1 + at.x, a.y1 + at.y};
    if (glow_step(view, c, plane, was) == glow_step(view, c, plane, beam)) continue;
    lv_area_t blip{(int) plane.x - reach, (int) plane.y - reach, (int) plane.x + reach, (int) plane.y + reach};
    lv_obj_invalidate_area(view->layer, &blip);
  }
}
// A scope whose beam turns draws itself again as the beam goes round, as a radar does: a new report, or a plane that
// glides, shows where the beam passes it, and the whole layer is never drawn again at once (a full screen of it is a
// seventh of a second, a stall in the beam).
static bool sweeps(const View *view) { return view->overlay.radar.on && view->overlay.radar.sweep && view->sweeping; }
static void stop_sweep(View *view) {
  if (view->sweeping) lv_timer_delete(view->sweeping);
  view->sweeping = nullptr;
  view->beam_drawn = -1;
}

static void deleted(lv_event_t *e) {
  auto *view = static_cast<View *>(lv_event_get_user_data(e));
  if (!view) return;
  view->layer = nullptr;
  stop_sweep(view);
}

void follow(View *view, lv_obj_t *picture) {
  if (!view || !view->layer || !picture) return;
  lv_obj_update_layout(picture);
  const int w = lv_obj_get_width(picture), h = lv_obj_get_height(picture);
  // Set only when they change: LVGL sets a size or a place through the object's style, which draws the whole object
  // again even when the value is the one it had, the whole glass on a full view, with every report.
  const bool resized = w != lv_obj_get_width(view->layer) || h != lv_obj_get_height(view->layer);
  const bool was_shown = !lv_obj_has_flag(view->layer, LV_OBJ_FLAG_HIDDEN);
  if (resized) lv_obj_set_size(view->layer, w, h);
  lv_area_t at, own;
  lv_obj_get_coords(picture, &at);
  lv_obj_get_coords(view->layer, &own);
  if (resized || at.x1 != own.x1 || at.y1 != own.y1) lv_obj_align_to(view->layer, picture, LV_ALIGN_TOP_LEFT, 0, 0);
  const int index = lv_obj_get_index(picture);
  if (index >= 0 && lv_obj_get_index(view->layer) != index + 1) lv_obj_move_to_index(view->layer, index + 1);
  view->sx = view->overlay.width > 0 ? (float) w / view->overlay.width : 1;
  view->sy = view->overlay.height > 0 ? (float) h / view->overlay.height : 1;
  const bool shown = !view->hidden && !lv_obj_has_flag(picture, LV_OBJ_FLAG_HIDDEN);
  if (shown) lv_obj_remove_flag(view->layer, LV_OBJ_FLAG_HIDDEN);
  else lv_obj_add_flag(view->layer, LV_OBJ_FLAG_HIDDEN);
  if (!sweeps(view) || resized || shown != was_shown) lv_obj_invalidate(view->layer);
}

void show(View *&view, lv_obj_t *picture, const ap::Overlay &o) {
  if (!picture) return;
  lv_obj_t *parent = lv_obj_get_parent(picture);
  if (!view) view = new View();
  if (view->layer && lv_obj_get_parent(view->layer) != parent) {
    lv_obj_delete(view->layer);
    view->layer = nullptr;
  }
  if (!view->layer) {
    view->layer = lv_obj_create(parent);
    lv_obj_remove_style_all(view->layer);
    lv_obj_remove_flag(view->layer, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_remove_flag(view->layer, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(view->layer, LV_OBJ_FLAG_IGNORE_LAYOUT);
    lv_obj_add_event_cb(view->layer, draw, LV_EVENT_DRAW_MAIN, view);
    lv_obj_add_event_cb(view->layer, deleted, LV_EVENT_DELETE, view);
  }
  view->overlay = o;
  if (o.radar.on && o.radar.sweep && !view->sweeping) view->sweeping = lv_timer_create(sweep, ap::SWEEP_FRAME_MS, view);
  else if (!(o.radar.on && o.radar.sweep)) stop_sweep(view);
  follow(view, picture);
}

void set_hidden(View *view, bool hidden) {
  if (!view || view->hidden == hidden) return;
  view->hidden = hidden;
  if (!view->layer) return;
  if (hidden) lv_obj_add_flag(view->layer, LV_OBJ_FLAG_HIDDEN);
  else lv_obj_remove_flag(view->layer, LV_OBJ_FLAG_HIDDEN);
}

void release(View *&view) {
  if (!view) return;
  stop_sweep(view);
  if (view->layer) {
    // Its user data goes first, so the delete event finds no view to write to.
    lv_obj_remove_event_cb_with_user_data(view->layer, deleted, view);
    lv_obj_delete(view->layer);
  }
  delete view;
  view = nullptr;
}

std::string pick(View *view, int x, int y, int reach) {
  if (!view || !view->layer || view->hidden) return "";
  lv_area_t a;
  lv_obj_get_coords(view->layer, &a);
  return ap::pick(view->overlay, (float) (x - a.x1), (float) (y - a.y1), (float) reach, lv_tick_get(), view->sx, view->sy);
}

bool where(View *view, const std::string &id, int &x, int &y) {
  if (!view || !view->layer || view->hidden || id.empty()) return false;
  for (const auto &p : view->overlay.planes) {
    if (p.id != id) continue;
    lv_area_t a;
    lv_obj_get_coords(view->layer, &a);
    const ap::Point at = ap::at(view->overlay, p, lv_tick_get(), view->sx, view->sy);
    x = a.x1 + (int) std::lround(at.x);
    y = a.y1 + (int) std::lround(at.y);
    return true;
  }
  return false;
}

void set_picked(View *view, const std::string &id) {
  if (!view || view->picked == id) return;
  view->picked = id;
  if (view->layer) lv_obj_invalidate(view->layer);
}

void tick(View *view, uint32_t now) {
  if (!view || !view->layer || view->hidden || !view->overlay.glide || view->overlay.planes.empty() || sweeps(view)) return;
  // Gliding until GLIDE_MS after the report, then once more where it stopped.
  if (now - view->overlay.at > ap::GLIDE_MS + 1000) return;
  lv_obj_invalidate(view->layer);
}
}  // namespace aircraft_view
