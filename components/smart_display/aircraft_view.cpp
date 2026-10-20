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
};

// A plane's colour: its band of altitude in the flight map's rainbow, or the screen's accent.
static lv_color_t colour_of(const ap::Overlay &o, int band) {
  static constexpr theme::Role BANDS[ap::BANDS] = {theme::AIRCRAFT_GROUND, theme::AIRCRAFT_LOW, theme::AIRCRAFT_MID,
                                                   theme::AIRCRAFT_HIGH, theme::AIRCRAFT_TOP};
  if (!o.by_altitude) return theme::color(theme::ACCENT);
  return theme::color(band >= 0 && band < ap::BANDS ? BANDS[band] : theme::AIRCRAFT_GROUND);
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
static void dot(lv_layer_t *layer, ap::Point c, int d, lv_color_t fill, int border, lv_color_t edge) {
  lv_draw_rect_dsc_t dsc;
  lv_draw_rect_dsc_init(&dsc);
  dsc.radius = LV_RADIUS_CIRCLE; dsc.bg_color = fill; dsc.bg_opa = LV_OPA_COVER;
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

static void draw(lv_event_t *e) {
  auto *view = static_cast<View *>(lv_event_get_user_data(e));
  if (!view || view->hidden) return;
  lv_layer_t *layer = lv_event_get_layer(e);
  lv_area_t a;
  lv_obj_get_coords(lv_event_get_target_obj(e), &a);
  const ap::Overlay &o = view->overlay;
  const Sizes s = sizes(o.full);
  const uint32_t now = lv_tick_get();
  const lv_color_t halo = theme::color(theme::CARD);
  auto on_glass = [&](float x, float y) { return ap::Point{a.x1 + x * view->sx, a.y1 + y * view->sy}; };
  std::vector<ap::Point> places;
  places.reserve(o.planes.size());
  for (const auto &p : o.planes) {
    const ap::Point at = ap::at(o, p, now, view->sx, view->sy);
    places.push_back({a.x1 + at.x, a.y1 + at.y});
  }
  // The tracks first, under every marker: from the oldest place to where the plane is now.
  for (size_t i = 0; i < o.planes.size(); ++i) {
    const auto &track = o.planes[i].track;
    if (track.size() < 4) continue;
    const lv_color_t colour = colour_of(o, o.planes[i].band);
    const size_t points = track.size() / 2;
    for (size_t n = 0; n + 1 < points; ++n) {
      const ap::Point from = on_glass(track[2 * n], track[2 * n + 1]);
      const ap::Point to = n + 2 == points ? places[i] : on_glass(track[2 * n + 2], track[2 * n + 3]);
      line(layer, from, to, colour, s.line, LV_OPA_70, n == 0, n + 2 == points);
    }
  }
  for (size_t i = 0; i < o.planes.size(); ++i) {
    const auto &p = o.planes[i];
    const lv_color_t colour = colour_of(o, p.band);
    const ap::Point c = places[i];
    if (o.marker == ap::PLANE && p.heading != ap::NO_HEADING) {
      // A halo in the card's colour, so the plane reads on streets and on water alike.
      shape(layer, c, s.plane + 2 * s.halo, p.heading, halo, LV_OPA_80);
      shape(layer, c, s.plane, p.heading, colour, LV_OPA_COVER);
      continue;
    }
    if (o.marker == ap::ARROW && p.heading != ap::NO_HEADING) {
      const auto tick = ap::heading_tick(c, s.dot / 2.0f, s.tick, p.heading);
      line(layer, tick[0], tick[1], halo, s.line + 2 * s.halo, LV_OPA_80);
      line(layer, tick[0], tick[1], colour, s.line, LV_OPA_COVER);
    }
    dot(layer, c, s.dot, colour, s.halo, halo);
  }
  // The labels last, over everything: a soft pill of the card's colour with the plane's lines in ink.
  const lv_font_t *font = o.full && rt::label_font ? rt::label_font : rt::small_font ? rt::small_font : rt::label_font;
  if (!font) return;
  const int line_h = lv_font_get_line_height(font);
  const int frame_w = lv_area_get_width(&a), frame_h = lv_area_get_height(&a);
  const int reach = (o.marker == ap::PLANE ? s.plane : s.dot) / 2;
  for (size_t i = 0; i < o.planes.size(); ++i) {
    const auto rows = ap::lines(o.planes[i].label);
    if (rows.empty()) continue;
    int w = 0;
    for (const auto &row : rows) w = std::max(w, rt::text_width(row, font));
    const int box_w = w + 2 * s.pad, box_h = (int) rows.size() * line_h + s.pad;
    const ap::Box box = ap::label_box({places[i].x - a.x1, places[i].y - a.y1}, reach, box_w, box_h, frame_w, frame_h, s.gap);
    lv_draw_rect_dsc_t bg;
    lv_draw_rect_dsc_init(&bg);
    bg.radius = s.radius; bg.bg_color = halo; bg.bg_opa = LV_OPA_80;
    lv_area_t area{a.x1 + box.x, a.y1 + box.y, a.x1 + box.x + box.w - 1, a.y1 + box.y + box.h - 1};
    lv_draw_rect(layer, &bg, &area);
    for (size_t n = 0; n < rows.size(); ++n) {
      lv_draw_label_dsc_t dsc;
      lv_draw_label_dsc_init(&dsc);
      dsc.font = font; dsc.color = theme::color(n ? theme::MUTED : theme::INK); dsc.text = rows[n].c_str();
      dsc.text_local = 1;
      const int y = area.y1 + s.pad / 2 + (int) n * line_h;
      lv_area_t text{area.x1 + s.pad, y, area.x2 - s.pad, y + line_h - 1};
      lv_draw_label(layer, &dsc, &text);
    }
  }
}

static void deleted(lv_event_t *e) {
  auto *view = static_cast<View *>(lv_event_get_user_data(e));
  if (view) view->layer = nullptr;
}

void follow(View *view, lv_obj_t *picture) {
  if (!view || !view->layer || !picture) return;
  lv_obj_update_layout(picture);
  const int w = lv_obj_get_width(picture), h = lv_obj_get_height(picture);
  lv_obj_set_size(view->layer, w, h);
  lv_obj_align_to(view->layer, picture, LV_ALIGN_TOP_LEFT, 0, 0);
  const int index = lv_obj_get_index(picture);
  if (index >= 0 && lv_obj_get_index(view->layer) != index + 1) lv_obj_move_to_index(view->layer, index + 1);
  view->sx = view->overlay.width > 0 ? (float) w / view->overlay.width : 1;
  view->sy = view->overlay.height > 0 ? (float) h / view->overlay.height : 1;
  const bool shown = !view->hidden && !lv_obj_has_flag(picture, LV_OBJ_FLAG_HIDDEN);
  if (shown) lv_obj_remove_flag(view->layer, LV_OBJ_FLAG_HIDDEN);
  else lv_obj_add_flag(view->layer, LV_OBJ_FLAG_HIDDEN);
  lv_obj_invalidate(view->layer);
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
  if (view->layer) {
    // Its user data goes first, so the delete event finds no view to write to.
    lv_obj_remove_event_cb_with_user_data(view->layer, deleted, view);
    lv_obj_delete(view->layer);
  }
  delete view;
  view = nullptr;
}

void tick(View *view, uint32_t now) {
  if (!view || !view->layer || view->hidden || !view->overlay.glide || view->overlay.planes.empty()) return;
  // Gliding until GLIDE_MS after the report, then once more where it stopped.
  if (now - view->overlay.at > ap::GLIDE_MS + 1000) return;
  lv_obj_invalidate(view->layer);
}
}  // namespace aircraft_view
