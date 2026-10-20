import { getStaticFiles } from "remotion"

let names: Set<string> | null = null

// True when public/<path> exists. The public file list is baked into the Studio page and render bundles (empty in
// the Player and in Node). Used so drafts render before the music, VO or mix exist.
export function hasStaticFile(path: string): boolean {
  if (names === null) names = new Set(getStaticFiles().map((file) => file.name))
  return names.has(path)
}
