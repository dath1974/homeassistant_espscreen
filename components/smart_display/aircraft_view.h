#pragma once
// Aircraft over a map's picture on the glass (docs/MAP.md, "Aircraft"): aircraft_plan.h's planes painted in one object
// that lies over the picture, in that object's draw event, on a map tile's card and on a map's full view.
#include "lvgl.h"
#include "aircraft_plan.h"

#include <string>

namespace aircraft_view {
struct View;  // the object over a picture and the planes it shows
// Lays `o` over `picture`: in the picture's parent, just above it, at its place and size. Creates the view the first
// time; afterwards only its planes change.
void show(View *&view, lv_obj_t *picture, const aircraft_plan::Overlay &o);
// The picture moved or took another size (a new picture of the same card): the view follows it.
void follow(View *view, lv_obj_t *picture);
// Shown or hidden without losing its planes (a full view's picture of another move, on its way).
void set_hidden(View *view, bool hidden);
// The card shows something else, or went: its object goes, if it is still there, and the view with it.
void release(View *&view);
// The id of the plane nearest a finger at `x`, `y` on the glass, within `reach` pixels of it; "" for none (a full view's).
std::string pick(View *view, int x, int y, int reach);
// Where plane `id` is on the glass now, false when the view has no such plane.
bool where(View *view, const std::string &id, int &x, int &y);
// The plane picked on a full view, ringed; "" for none.
void set_picked(View *view, const std::string &id);
// Every second (runtime_tiles::tick): planes that glide are drawn where they are now.
void tick(View *view, uint32_t now);
// A radar scope's colours (theme.h radar::TINTS): its phosphor at `light` (0 the ground, 1 the glow, 2 the hottest
// light), and its ground, for what lies over a scope in its style (the card of a plane picked, the name over it).
lv_color_t phosphor(const aircraft_plan::Overlay &o, float light);
lv_color_t ground(const aircraft_plan::Overlay &o);
}  // namespace aircraft_view
