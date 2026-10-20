<script setup lang="ts">
// A map card's settings (app 0.4.33, docs/MAP.md; the map tile and these choices 0.4.36): whom it follows, who rides
// along beside the tile's own person, how it frames them and how far a fixed view reaches, how it looks, and its name on
// the picture. The choices are the catalogue's (catalogue/person.yaml), the first of each the default.
import { computed } from "vue";
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
import { AIR_CHOICES, AIR_NUMBERS } from "../../model/aircraft";
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
const framing = computed(() => current("framing", MAP?.framing[0]) as string);
type MapChoice = "framing" | "distance" | "follow" | "markers" | "names" | "zones" | "streets" | "look";
const choices = (key: MapChoice) => offeredChoices(props.tile, key, (MAP?.[key] ?? [])
  // Around this person is a person's map: the map tile has no person of its own.
  .filter((value) => !(key === "framing" && value === "person" && mapTile.value))
  .map((value) => [value, t(`editor.tile.map.${key}.${value}`)] as [string, string]), current(key, MAP?.[key][0]), controlled.value);
const overlay = computed(() => offeredChoices(props.tile, "overlay", rules.picture.overlay.map((value) => [value, t(`editor.tile.picture.overlay.${value}`)] as [string, string]),
  current("overlay", rules.picture.overlay[0]), controlled.value));
// Aircraft over the map tile (docs/MAP.md, "Aircraft"): a sensor that lists flights, as Flightradar24's Current in
// area does, and how the screen draws them.
const source = computed(() => (props.tile.options?.aircraft as string | undefined) ?? "");
const sources = computed(() => (inv.inventory.aircraft || []).map((item) => ({ id: item.id, name: item.name || item.id, hint: item.id })));
const sourceName = computed(() => source.value ? entities.entityName(source.value) : t("editor.tile.map.aircraft.choose"));
type AirChoice = "plane_marker" | "plane_label" | "plane_colour" | "plane_ground" | "plane_motion" | "plane_track";
const airChoices = (key: AirChoice) => offeredChoices(props.tile, key, (AIR_CHOICES[key] ?? [])
  .map((value) => [value, t(`editor.tile.map.aircraft.${key}.${value}`)] as [string, string]), current(key, AIR_CHOICES[key]?.[0]), controlled.value);
const airValue = (key: string) => current(key, AIR_CHOICES[key]?.[0] ?? AIR_NUMBERS[key]?.[0]);
// A whole number typed over: kept within its range, the default when the field is left empty.
function setNumber(key: string, text: string) {
  const [first, low, high] = AIR_NUMBERS[key] ?? [0, 0, 0];
  const value = text.trim() === "" ? first : Math.round(Number(text.replace(/[^0-9]/g, "")));
  setTileOption(props.tile, key, Number.isFinite(value) ? Math.max(low, Math.min(high, value)) : first);
}
function add(id: string) { if (id) setTileOption(props.tile, "map", [...mapWith.value, id]); }
function remove(id: string) { setTileOption(props.tile, "map", mapWith.value.filter((item) => item !== id)); }
</script>

<template>
  <Section :title="t('editor.tile.display.map')">
    <p v-if="mapTile" class="hint">{{ t(scr.supports(0, 21, 0) ? "editor.tile.display.map_hint" : "editor.tile.display.map_tile_needs_firmware") }}</p>
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
    <PropRow :label="t('editor.tile.map.framing.label')" icon="crosshairs-gps">
      <ChoiceField :choices="choices('framing')" :value="framing" :tile="tile" preview-key="framing" :aria-label="t('editor.tile.map.framing.label')" @pick="(v) => setTileOption(tile, 'framing', v)" />
    </PropRow>
    <PropRow v-if="framing !== 'everyone'" :label="t('editor.tile.map.distance.label')" icon="magnify-plus-outline">
      <ChoiceField :choices="choices('distance')" :value="current('distance', MAP?.distance[0])" :tile="tile" preview-key="distance" :aria-label="t('editor.tile.map.distance.label')" @pick="(v) => setTileOption(tile, 'distance', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.map.markers.label')" icon="account-circle-outline">
      <ChoiceField :choices="choices('markers')" :value="current('markers', MAP?.markers[0])" :tile="tile" preview-key="markers" :aria-label="t('editor.tile.map.markers.label')" @pick="(v) => setTileOption(tile, 'markers', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.map.names.label')" icon="label-outline">
      <ChoiceField :choices="choices('names')" :value="current('names', MAP?.names[0])" :tile="tile" preview-key="names" :aria-label="t('editor.tile.map.names.label')" @pick="(v) => setTileOption(tile, 'names', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.map.zones.label')" icon="map-marker-radius-outline">
      <ChoiceField :choices="choices('zones')" :value="current('zones', MAP?.zones[0])" :tile="tile" preview-key="zones" :aria-label="t('editor.tile.map.zones.label')" @pick="(v) => setTileOption(tile, 'zones', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.map.streets.label')" icon="road-variant">
      <ChoiceField :choices="choices('streets')" :value="current('streets', MAP?.streets[0])" :tile="tile" preview-key="streets" :aria-label="t('editor.tile.map.streets.label')" @pick="(v) => setTileOption(tile, 'streets', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.map.look.label')" icon="theme-light-dark">
      <ChoiceField :choices="choices('look')" :value="current('look', MAP?.look[0])" :tile="tile" preview-key="look" :aria-label="t('editor.tile.map.look.label')" @pick="(v) => setTileOption(tile, 'look', v)" />
    </PropRow>
    <template v-if="mapTile">
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
      </template>
    </template>
    <PropRow :label="t('editor.tile.picture.overlay.label')" icon="format-title">
      <ChoiceField :choices="overlay" :value="current('overlay', 'name')" :tile="tile" preview-key="overlay" :aria-label="t('editor.tile.picture.overlay.label')" @pick="(v) => setTileOption(tile, 'overlay', v)" />
    </PropRow>
  </Section>
</template>
