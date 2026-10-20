/** Aircraft over the map tile (docs/MAP.md, "Aircraft"): the sensor they come from and how the screen draws them, as
 * screen_manager/app/aircraft.py checks them. The choices are the catalogue's (catalogue/person.yaml `map.aircraft`): a
 * list of words, the first the default, or [default, lowest, highest] of a whole number. A default is never stored. */
import { ofType } from "./catalogue";

/** The page document's names (appearance) of the tile options, as page_layout.APPEARANCE has them. */
export const AIR_APPEARANCE = { airSource: "aircraft", airMarker: "plane_marker", airLabel: "plane_label", airColour: "plane_colour",
  airGround: "plane_ground", airMotion: "plane_motion", airTrack: "plane_track", airTrackSeconds: "plane_track_s",
  airMost: "plane_most", airMin: "plane_min", airMax: "plane_max" } as const;
export type AirField = keyof typeof AIR_APPEARANCE;
export type AirOption = (typeof AIR_APPEARANCE)[AirField];
export const AIR_FIELDS = Object.keys(AIR_APPEARANCE) as AirField[];
export const AIR_OWN = Object.values(AIR_APPEARANCE) as AirOption[];

const AIRCRAFT = (ofType("person")?.map as { aircraft?: Record<string, (string | number)[]> } | undefined)?.aircraft ?? {};
/** The whole numbers: [default, lowest, highest]. */
export const AIR_NUMBERS = Object.fromEntries(Object.entries(AIRCRAFT).filter(([, v]) => v.every((n) => typeof n === "number"))) as
  Record<string, [number, number, number]>;
/** The words, the first the default. */
export const AIR_CHOICES = Object.fromEntries(Object.entries(AIRCRAFT).filter(([key]) => !(key in AIR_NUMBERS))) as Record<string, string[]>;
/** What each option means when it is not stored. */
export const AIR_DEFAULTS: Record<string, unknown> = {
  ...Object.fromEntries(Object.entries(AIR_CHOICES).map(([key, values]) => [key, values[0]])),
  ...Object.fromEntries(Object.entries(AIR_NUMBERS).map(([key, [first]]) => [key, first])),
};
const SOURCE = /^sensor\.[a-z0-9_]+$/;

/** The reason a tile's aircraft options would be refused or changed by the add-on (aircraft.validate), or "". */
export function airProblem(options: Record<string, unknown>, mapTile: boolean): "" | "normalization" | "invalid" {
  const used = AIR_OWN.filter((key) => options[key] !== undefined);
  if (!used.length) return "";
  if (!mapTile) return "normalization";
  const source = options.aircraft;
  if (source !== undefined && (typeof source !== "string" || !SOURCE.test(source) || source.length > 255)) return "invalid";
  for (const [key, values] of Object.entries(AIR_CHOICES)) {
    if (options[key] === undefined) continue;
    if (!values.includes(options[key] as string)) return "invalid";
    if (options[key] === values[0]) return "normalization";
  }
  for (const [key, [first, low, high]] of Object.entries(AIR_NUMBERS)) {
    const value = options[key];
    if (value === undefined) continue;
    if (typeof value !== "number" || !Number.isInteger(value) || value < low || value > high) return "invalid";
    if (value === first) return "normalization";
  }
  const low = (options.plane_min as number | undefined) ?? AIR_NUMBERS.plane_min?.[0] ?? 0;
  const high = (options.plane_max as number | undefined) ?? AIR_NUMBERS.plane_max?.[0] ?? 0;
  return low > high ? "invalid" : "";
}
