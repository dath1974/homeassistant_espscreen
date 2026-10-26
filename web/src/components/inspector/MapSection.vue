<script setup lang="ts">
// A map card's settings (app 0.4.33, docs/MAP.md; the map tile and these choices 0.4.36): in three groups. The map
// itself: what the map tile shows (people, aircraft or both), where it is centred and how far it reaches, how it looks,
// and its name on the picture. Its people: whom it follows and who rides along, their markers and names. The map tile's
// aircraft. The choices are the catalogue's (catalogue/person.yaml), the first of each the default.
import { computed, ref, watch } from "vue";
import theme from "virtual:esp-screens-theme";
import { getJson } from "../../api";
import { t } from "../../i18n";
import { ofType } from "../../model/catalogue";
import rules from "../../model/page-rules.json";
import { offeredChoices } from "../../model/tile-options";
import type { Tile } from "../../types";
import ChoiceField from "../ChoiceField.vue";
import Icon from "../ui/Icon.vue";
import PropRow from "../ui/PropRow.vue";
import Section from "../ui/Section.vue";
import UiSelect from "../ui/UiSelect.vue";
import UiPicker from "../ui/UiPicker.vue";
import { AIR_CHOICES, AIR_NUMBERS, WATCH_COLOURS, WATCH_MOST, watchId, watchKey, type Watched } from "../../model/aircraft";
import { setTileOption } from "../../editor/tiles";
import { useEntitiesStore } from "../../stores/entities";
import { useInventoryStore } from "../../stores/inventory";
import { useScreenStore } from "../../stores/screen";

const entities = useEntitiesStore();
const inv = useInventoryStore();
const scr = useScreenStore();
const props = defineProps<{ tile: Tile }>();

const MAP = ofType("person")?.map;
const current = (key: string, fallback: unknown) => props.tile.options?.[key] ?? fallback;
const controlled = computed(() => Boolean(inv.inventory.controls?.[props.tile.entity.split(".")[0]]));
const mapWith = computed(() => (props.tile.options?.map as string[] | undefined) ?? []);
// The map tile of the screen's own cards (app 0.4.36): no person of its own, following everyone or whom it lists.
const mapTile = computed(() => props.tile.entity === "screen.map");
const follow = computed(() => current("follow", MAP?.follow[0]) as string);
const listed = computed(() => !mapTile.value || follow.value === "chosen");
const full = computed(() => mapWith.value.length >= (MAP?.max ?? 8) - (mapTile.value ? 0 : 1));
const offered = computed(() => [...(inv.inventory.entities || []), ...(inv.inventory.trackers || [])]
  .filter((item) => (MAP?.with ?? []).includes(item.id.split(".")[0]) && item.id !== props.tile.entity && !mapWith.value.includes(item.id))
  .map((item) => [item.id, item.name || item.id] as [string, string]));
// What the map tile shows (map_card.people_shown, aircraft.source_of): its people, its aircraft or both.
const show = computed(() => (mapTile.value ? current("show", MAP?.show?.[0] ?? "both") : "people") as string);
const people = computed(() => show.value !== "aircraft");
const planes = computed(() => mapTile.value && show.value !== "people");
// A map without its people has nobody to fit: it is around home, as map_card.frame_view frames it then.
const framing = computed(() => {
  const value = current("framing", MAP?.framing[0]) as string;
  return !people.value && value === "everyone" ? "home" : value;
});
type MapChoice = "framing" | "distance" | "follow" | "markers" | "names" | "zones" | "streets" | "scope" | "look" | "show";
const choices = (key: MapChoice) => offeredChoices(props.tile, key, (MAP?.[key] ?? [])
  // Around this person is a person's map: the map tile has no person of its own. Everyone needs people on the map.
  .filter((value) => !(key === "framing" && value === "person" && mapTile.value))
  .filter((value) => !(key === "framing" && value === "everyone" && !people.value))
  .map((value) => [value, t(`editor.tile.map.${key}.${value}`)] as [string, string]), current(key, MAP?.[key]?.[0]), controlled.value);
// A chart in place of the streets (map_charts.py): the FAA's or the USGS's, United States only.
const charted = computed(() => !["show", "hide", "radar"].includes(current("streets", MAP?.streets[0]) as string));
// A radar scope in place of the streets (map_card.draw_scope): lit in its own phosphor whatever the look, and on its
// full view a beam that can turn.
const radar = computed(() => current("streets", MAP?.streets[0]) === "radar");
// What a tap on the map tile does: the full view with its keys, the map alone over the whole glass (`clean`, closed by
// another tap), or nothing. The catalogue's screen taps; the tile's other taps mean nothing on a map.
const tap = computed(() => current("tap", "auto") as string);
const tapChoices = computed(() => (["auto", "clean", "none"] as const).map((value) => [value, t(`editor.tile.map.tap.${value}`)] as [string, string]));
const overlay = computed(() => offeredChoices(props.tile, "overlay", rules.picture.overlay.map((value) => [value, t(`editor.tile.picture.overlay.${value}`)] as [string, string]),
  current("overlay", rules.picture.overlay[0]), controlled.value));
// The middle of a map framed on a place of its own, typed in one field: "latitude, longitude" (as a map site copies it),
// stored as two numbers, or an airport's code (KJFK, LAX, EGLL), which the app looks up (airports.py) and stores as the
// code; the field then names the airport and gives its latitude and longitude.
const centre = computed(() => props.tile.options?.centre as number[] | string | undefined);
type Airport = { code: string; name: string; lat: number; lon: number };
const place = ref(""), placeFound = ref<Airport | null>(null), placeWrong = ref(false);
async function airport(code: string): Promise<Airport | null> {
  try { return await getJson(`airport?code=${encodeURIComponent(code)}`); } catch { return null; }
}
watch(centre, async (value) => {
  placeWrong.value = false;
  placeFound.value = null;
  if (Array.isArray(value) && value.length === 2) place.value = `${value[0]}, ${value[1]}`;
  else if (typeof value === "string") {
    place.value = value;
    const found = await airport(value);
    if (centre.value === value) placeFound.value = found;
  } else place.value = "";
}, { immediate: true });
async function setPlace(text: string) {
  const typed = text.trim();
  place.value = typed;
  placeWrong.value = false;
  if (!typed) { setTileOption(props.tile, "centre", undefined); return; }
  const pair = typed.split(/[,;\s]+/).filter(Boolean);
  if (pair.length === 2 && pair.every((v) => /^[-+]?\d+(\.\d+)?$/.test(v))) {
    const [a, b] = pair.map(Number);
    if (Math.abs(a) <= 85 && Math.abs(b) <= 180) setTileOption(props.tile, "centre", [Math.round(a * 1e5) / 1e5, Math.round(b * 1e5) / 1e5]);
    else placeWrong.value = true;
    return;
  }
  const found = await airport(typed);
  if (place.value !== typed) return;
  if (found) setTileOption(props.tile, "centre", found.code);
  else placeWrong.value = true;
}
// How far the distance `radius` reaches: stored in metres, typed in Home Assistant's unit (km or mi), to a tenth.
const miles = computed(() => inv.inventory.units?.length === "mi");
const METRES = computed(() => (miles.value ? 1609.344 : 1000));
const RADIUS = MAP?.radius ?? [10000, 200, 500000];
const radius = computed(() => String(Math.round(((current("radius", RADIUS[0]) as number) / METRES.value) * 10) / 10));
function setRadius(text: string) {
  const value = Number(text.replace(",", "."));
  if (!text.trim() || !Number.isFinite(value)) { setTileOption(props.tile, "radius", RADIUS[0]); return; }
  setTileOption(props.tile, "radius", Math.max(RADIUS[1], Math.min(RADIUS[2], Math.round(value * METRES.value))));
}
// Aircraft over the map tile (docs/MAP.md, "Aircraft"): a sensor that lists flights, as Flightradar24's Current in
// area does, and how the screen draws them.
const source = computed(() => (props.tile.options?.aircraft as string | undefined) ?? "");
const sources = computed(() => (inv.inventory.aircraft || []).map((item) => ({ id: item.id, name: item.name || item.id, hint: item.id })));
const sourceName = computed(() => source.value ? entities.entityName(source.value) : t("editor.tile.map.aircraft.choose"));
type AirChoice = "plane_marker" | "plane_label" | "plane_colour" | "plane_ground" | "plane_motion" | "plane_track" | "plane_sweep";
const airChoices = (key: AirChoice) => offeredChoices(props.tile, key, (AIR_CHOICES[key] ?? [])
  .map((value) => [value, t(`editor.tile.map.aircraft.${key}.${value}`)] as [string, string]), current(key, AIR_CHOICES[key]?.[0]), controlled.value);
const airValue = (key: string) => current(key, AIR_CHOICES[key]?.[0] ?? AIR_NUMBERS[key]?.[0]);
// A whole number typed over: kept within its range, the default when the field is left empty.
function setNumber(key: string, text: string) {
  const [first, low, high] = AIR_NUMBERS[key] ?? [0, 0, 0];
  const value = text.trim() === "" ? first : Math.round(Number(text.replace(/[^0-9]/g, "")));
  setTileOption(props.tile, key, Number.isFinite(value) ? Math.max(low, Math.min(high, value)) : first);
}
// Watched aircraft: a registration or callsign each, in a colour of its own (Home Assistant's, theme.h ha::), the next
// unused colour for one added.
const watched = computed(() => (props.tile.options?.plane_watch as Watched[] | undefined) ?? []);
const HA: Record<string, string> = { red: "RED", orange: "ORANGE", amber: "AMBER", green: "GREEN", blue: "BLUE", purple: "PURPLE" };
const swatch = (colour: string) => `#${(theme.ha[HA[colour]] ?? 0).toString(16).padStart(6, "0")}`;
const colours = computed(() => WATCH_COLOURS.map((colour) => [colour, t(`editor.tile.map.aircraft.watch.colours.${colour}`)] as [string, string]));
const typed = ref("");
const typedWrong = computed(() => Boolean(typed.value.trim()) && !watchId(typed.value));
function addWatched() {
  const id = watchId(typed.value);
  if (!id || watched.value.length >= WATCH_MOST) return;
  typed.value = "";
  if (watched.value.some((item) => watchKey(item.id) === watchKey(id))) return;
  const used = new Set(watched.value.map((item) => item.colour));
  const colour = WATCH_COLOURS.find((c) => !used.has(c)) ?? WATCH_COLOURS[watched.value.length % WATCH_COLOURS.length];
  setTileOption(props.tile, "plane_watch", [...watched.value, { id, colour }]);
}
function recolour(index: number, colour: string) {
  setTileOption(props.tile, "plane_watch", watched.value.map((item, n) => (n === index ? { ...item, colour } : item)));
}
function unwatch(index: number) {
  const rest = watched.value.filter((_, n) => n !== index);
  setTileOption(props.tile, "plane_watch", rest.length ? rest : undefined);
}
function add(id: string) { if (id) setTileOption(props.tile, "map", [...mapWith.value, id]); }
function remove(id: string) { setTileOption(props.tile, "map", mapWith.value.filter((item) => item !== id)); }
</script>

<template>
  <Section :title="t('editor.tile.display.map')">
    <p v-if="mapTile" class="hint">{{ t(scr.supports(0, 21, 0) ? "editor.tile.display.map_hint" : "editor.tile.display.map_tile_needs_firmware") }}</p>
    <PropRow v-if="mapTile" :label="t('editor.tile.map.show.label')" icon="eye-outline">
      <ChoiceField :choices="choices('show')" :value="show" :tile="tile" preview-key="show" :aria-label="t('editor.tile.map.show.label')" @pick="(v) => setTileOption(tile, 'show', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.map.framing.label')" icon="crosshairs-gps">
      <ChoiceField :choices="choices('framing')" :value="framing" :tile="tile" preview-key="framing" :aria-label="t('editor.tile.map.framing.label')" @pick="(v) => setTileOption(tile, 'framing', v)" />
    </PropRow>
    <PropRow v-if="framing === 'place'" :label="t('editor.tile.map.centre.label')" icon="crosshairs" for="map-place" :hint="t('editor.tile.map.centre.hint')">
      <span class="map-place">
        <input id="map-place" class="map-number" :aria-invalid="placeWrong || undefined" :value="place" :placeholder="t('editor.tile.map.centre.placeholder')"
          autocomplete="off" spellcheck="false" aria-describedby="map-place-found"
          @change="setPlace(($event.target as HTMLInputElement).value)" @keydown.enter="($event.target as HTMLInputElement).blur()" />
        <small v-if="placeWrong" id="map-place-found" class="wrong">{{ t("editor.tile.map.centre.wrong") }}</small>
        <small v-else-if="placeFound" id="map-place-found">{{ placeFound.name }}<br /><span class="map-place-at">{{ placeFound.lat }}, {{ placeFound.lon }}</span></small>
      </span>
    </PropRow>
    <PropRow v-if="framing !== 'everyone'" :label="t('editor.tile.map.distance.label')" icon="magnify-plus-outline">
      <ChoiceField :choices="choices('distance')" :value="current('distance', MAP?.distance[0])" :tile="tile" preview-key="distance" :aria-label="t('editor.tile.map.distance.label')" @pick="(v) => setTileOption(tile, 'distance', v)" />
    </PropRow>
    <PropRow v-if="framing !== 'everyone' && current('distance', MAP?.distance[0]) === 'radius'" :label="t('editor.tile.map.radius.label')"
      icon="map-marker-radius-outline" for="map-radius"
      :hint="t('editor.tile.map.radius.hint', { low: Math.round((RADIUS[1] / METRES) * 10) / 10, high: Math.round(RADIUS[2] / METRES), unit: t(`editor.tile.map.radius.${miles ? 'mi' : 'km'}`) })">
      <span class="map-range">
        <input id="map-radius" class="map-number" inputmode="decimal" :value="radius"
          @change="setRadius(($event.target as HTMLInputElement).value)" @keydown.enter="($event.target as HTMLInputElement).blur()" />
        <label>{{ t(`editor.tile.map.radius.${miles ? "mi" : "km"}`) }}</label>
      </span>
    </PropRow>
    <PropRow :label="t('editor.tile.map.streets.label')" icon="map-outline" :hint="charted ? t('editor.tile.map.streets.chart_hint') : undefined">
      <ChoiceField :choices="choices('streets')" :value="current('streets', MAP?.streets[0])" :tile="tile" preview-key="streets" :aria-label="t('editor.tile.map.streets.label')" @pick="(v) => setTileOption(tile, 'streets', v)" />
    </PropRow>
    <PropRow v-if="radar" :label="t('editor.tile.map.scope.label')" icon="palette-outline" :hint="t('editor.tile.map.scope.hint')">
      <ChoiceField :choices="choices('scope')" :value="current('scope', MAP?.scope?.[0])" :tile="tile" preview-key="scope" :aria-label="t('editor.tile.map.scope.label')" @pick="(v) => setTileOption(tile, 'scope', v)" />
    </PropRow>
    <PropRow v-if="people" :label="t('editor.tile.map.zones.label')" icon="map-marker-radius-outline">
      <ChoiceField :choices="choices('zones')" :value="current('zones', MAP?.zones[0])" :tile="tile" preview-key="zones" :aria-label="t('editor.tile.map.zones.label')" @pick="(v) => setTileOption(tile, 'zones', v)" />
    </PropRow>
    <PropRow v-if="!radar" :label="t('editor.tile.map.look.label')" icon="theme-light-dark">
      <ChoiceField :choices="choices('look')" :value="current('look', MAP?.look[0])" :tile="tile" preview-key="look" :aria-label="t('editor.tile.map.look.label')" @pick="(v) => setTileOption(tile, 'look', v)" />
    </PropRow>
    <PropRow v-if="mapTile" :label="t('editor.tile.map.tap.label')" icon="gesture-tap" :hint="t(`editor.tile.map.tap.${tap}_hint`)">
      <ChoiceField :choices="tapChoices" :value="tap" :aria-label="t('editor.tile.map.tap.label')" @pick="(v) => setTileOption(tile, 'tap', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.picture.overlay.label')" icon="format-title">
      <ChoiceField :choices="overlay" :value="current('overlay', 'name')" :tile="tile" preview-key="overlay" :aria-label="t('editor.tile.picture.overlay.label')" @pick="(v) => setTileOption(tile, 'overlay', v)" />
    </PropRow>
  </Section>
  <Section v-if="people" :title="t('editor.tile.map.group.people')" icon="account-multiple-outline">
    <PropRow v-if="mapTile" :label="t('editor.tile.map.follow.label')" icon="account-eye-outline"
      :hint="follow === 'everyone' ? t('editor.tile.map.follow.everyone_hint') : undefined">
      <ChoiceField :choices="choices('follow')" :value="follow" :tile="tile" preview-key="follow" :aria-label="t('editor.tile.map.follow.label')" @pick="(v) => setTileOption(tile, 'follow', v)" />
    </PropRow>
    <PropRow v-if="listed" :label="t(mapTile ? 'editor.tile.map.chosen.label' : 'editor.tile.map.with.label')" icon="account-multiple-outline"
      :hint="t(mapTile ? 'editor.tile.map.chosen.hint' : 'editor.tile.map.with.hint')">
      <div class="map-with">
        <span v-for="item in mapWith" :key="item" class="map-person">
          {{ entities.entityName(item) }}
          <button type="button" class="map-remove" :aria-label="t('editor.tile.map.with.remove', { name: entities.entityName(item) })" @click="remove(item)"><Icon name="close" /></button>
        </span>
        <UiSelect v-if="!full && offered.length" class="map-add" :model-value="''" :options="offered"
          :placeholder="t('editor.tile.map.with.add')" :aria-label="t('editor.tile.map.with.add')" @update:model-value="add" />
      </div>
    </PropRow>
    <PropRow :label="t('editor.tile.map.markers.label')" icon="account-circle-outline">
      <ChoiceField :choices="choices('markers')" :value="current('markers', MAP?.markers[0])" :tile="tile" preview-key="markers" :aria-label="t('editor.tile.map.markers.label')" @pick="(v) => setTileOption(tile, 'markers', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.map.names.label')" icon="label-outline">
      <ChoiceField :choices="choices('names')" :value="current('names', MAP?.names[0])" :tile="tile" preview-key="names" :aria-label="t('editor.tile.map.names.label')" @pick="(v) => setTileOption(tile, 'names', v)" />
    </PropRow>
  </Section>
  <Section v-if="planes" :title="t('editor.tile.map.group.aircraft')" icon="map-outline">
    <PropRow :label="t('editor.tile.map.aircraft.label')" icon="map-outline" :hint="t(sources.length || source ? 'editor.tile.map.aircraft.hint' : 'editor.tile.map.aircraft.none')" stack>
      <UiPicker id="map-aircraft" :items="sources" :placeholder="t('editor.tile.map.aircraft.search')" :empty="t('editor.tile.map.aircraft.none_found')"
        @pick="(id: string) => setTileOption(tile, 'aircraft', id)">
        <template #trigger>
          <button type="button" class="ghost-btn"><Icon name="magnify" />{{ sourceName }}</button>
        </template>
      </UiPicker>
      <button v-if="source" type="button" class="btn quiet mini" :aria-label="t('editor.tile.map.aircraft.remove', { name: sourceName })"
        @click="setTileOption(tile, 'aircraft', '')"><Icon name="close" /></button>
    </PropRow>
    <template v-if="source">
      <PropRow :label="t('editor.tile.map.aircraft.plane_marker.label')" icon="checkbox-blank-circle-outline">
        <ChoiceField :choices="airChoices('plane_marker')" :value="airValue('plane_marker')" :tile="tile" preview-key="plane_marker" :aria-label="t('editor.tile.map.aircraft.plane_marker.label')" @pick="(v) => setTileOption(tile, 'plane_marker', v)" />
      </PropRow>
      <PropRow :label="t('editor.tile.map.aircraft.plane_label.label')" icon="label-outline">
        <ChoiceField :choices="airChoices('plane_label')" :value="airValue('plane_label')" :tile="tile" preview-key="plane_label" :aria-label="t('editor.tile.map.aircraft.plane_label.label')" @pick="(v) => setTileOption(tile, 'plane_label', v)" />
      </PropRow>
      <PropRow :label="t('editor.tile.map.aircraft.plane_colour.label')" icon="palette-outline">
        <ChoiceField :choices="airChoices('plane_colour')" :value="airValue('plane_colour')" :tile="tile" preview-key="plane_colour" :aria-label="t('editor.tile.map.aircraft.plane_colour.label')" @pick="(v) => setTileOption(tile, 'plane_colour', v)" />
      </PropRow>
      <PropRow :label="t('editor.tile.map.aircraft.plane_motion.label')" icon="play" :hint="t(`editor.tile.map.aircraft.plane_motion.${airValue('plane_motion')}_hint`)">
        <ChoiceField :choices="airChoices('plane_motion')" :value="airValue('plane_motion')" :tile="tile" preview-key="plane_motion" :aria-label="t('editor.tile.map.aircraft.plane_motion.label')" @pick="(v) => setTileOption(tile, 'plane_motion', v)" />
      </PropRow>
      <PropRow v-if="radar" :label="t('editor.tile.map.aircraft.plane_sweep.label')" icon="crosshairs" :hint="t('editor.tile.map.aircraft.plane_sweep.hint')">
        <ChoiceField :choices="airChoices('plane_sweep')" :value="airValue('plane_sweep')" :tile="tile" preview-key="plane_sweep" :aria-label="t('editor.tile.map.aircraft.plane_sweep.label')" @pick="(v) => setTileOption(tile, 'plane_sweep', v)" />
      </PropRow>
      <PropRow :label="t('editor.tile.map.aircraft.plane_track.label')" icon="gesture-swipe-horizontal">
        <ChoiceField :choices="airChoices('plane_track')" :value="airValue('plane_track')" :tile="tile" preview-key="plane_track" :aria-label="t('editor.tile.map.aircraft.plane_track.label')" @pick="(v) => setTileOption(tile, 'plane_track', v)" />
      </PropRow>
      <PropRow v-if="airValue('plane_track') === 'show'" :label="t('editor.tile.map.aircraft.plane_track_s.label')" icon="clock-outline" for="map-air-track"
        :hint="t('editor.tile.map.aircraft.plane_track_s.hint', { low: AIR_NUMBERS.plane_track_s?.[1], high: AIR_NUMBERS.plane_track_s?.[2] })">
        <input id="map-air-track" class="map-number" inputmode="numeric" :value="String(airValue('plane_track_s'))"
          @change="setNumber('plane_track_s', ($event.target as HTMLInputElement).value)" @keydown.enter="($event.target as HTMLInputElement).blur()" />
      </PropRow>
      <PropRow :label="t('editor.tile.map.aircraft.plane_ground.label')" icon="arrow-down">
        <ChoiceField :choices="airChoices('plane_ground')" :value="airValue('plane_ground')" :tile="tile" preview-key="plane_ground" :aria-label="t('editor.tile.map.aircraft.plane_ground.label')" @pick="(v) => setTileOption(tile, 'plane_ground', v)" />
      </PropRow>
      <PropRow :label="t('editor.tile.map.aircraft.altitude.label')" icon="arrow-up" :hint="t('editor.tile.map.aircraft.altitude.hint')">
        <span class="map-range">
          <label>{{ t("editor.tile.map.aircraft.altitude.min") }}<input class="map-number" inputmode="numeric" :value="String(airValue('plane_min'))"
            @change="setNumber('plane_min', ($event.target as HTMLInputElement).value)" @keydown.enter="($event.target as HTMLInputElement).blur()" /></label>
          <label>{{ t("editor.tile.map.aircraft.altitude.max") }}<input class="map-number" inputmode="numeric" :value="String(airValue('plane_max'))"
            @change="setNumber('plane_max', ($event.target as HTMLInputElement).value)" @keydown.enter="($event.target as HTMLInputElement).blur()" /></label>
        </span>
      </PropRow>
      <PropRow :label="t('editor.tile.map.aircraft.plane_most.label')" icon="filter-variant" for="map-air-most"
        :hint="t('editor.tile.map.aircraft.plane_most.hint', { high: AIR_NUMBERS.plane_most?.[2] })">
        <input id="map-air-most" class="map-number" inputmode="numeric" :value="String(airValue('plane_most'))"
          @change="setNumber('plane_most', ($event.target as HTMLInputElement).value)" @keydown.enter="($event.target as HTMLInputElement).blur()" />
      </PropRow>
      <PropRow :label="t('editor.tile.map.aircraft.watch.label')" icon="crosshairs" for="map-air-watch"
        :hint="t(typedWrong ? 'editor.tile.map.aircraft.watch.wrong' : 'editor.tile.map.aircraft.watch.hint', { most: WATCH_MOST })" stack>
        <div class="map-watch">
          <div v-for="(item, n) in watched" :key="item.id" class="map-watch-row">
            <span class="map-swatch" :style="{ background: swatch(item.colour) }" />
            <span class="map-watch-id">{{ item.id }}</span>
            <UiSelect class="map-watch-colour" :model-value="item.colour" :options="colours"
              :aria-label="t('editor.tile.map.aircraft.watch.colour', { name: item.id })" @update:model-value="(v) => recolour(n, String(v))" />
            <button type="button" class="map-remove" :aria-label="t('editor.tile.map.aircraft.watch.remove', { name: item.id })" @click="unwatch(n)"><Icon name="close" /></button>
          </div>
          <form v-if="watched.length < WATCH_MOST" class="map-watch-add" @submit.prevent="addWatched">
            <input id="map-air-watch" v-model="typed" class="map-number" autocapitalize="characters" spellcheck="false" maxlength="10"
              :placeholder="t('editor.tile.map.aircraft.watch.placeholder')" />
            <button type="submit" class="btn quiet mini" :disabled="!watchId(typed)">{{ t("editor.tile.map.aircraft.watch.add") }}</button>
          </form>
        </div>
      </PropRow>
    </template>
  </Section>
</template>
