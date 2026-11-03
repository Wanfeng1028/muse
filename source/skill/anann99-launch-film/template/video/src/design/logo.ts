// REPLACE with the brand mark. Paste the <path d="…"> strings and the viewBox from the logo SVG
// (scripts/capture-site.mjs saves inline header SVGs to public/site/logo-*.svg).
// BrandMark draws the outline (stroke-dash) and then fills it; it works best with filled single-colour marks.
// If you only have a raster logo, set PATHS to [] and BrandMark falls back to <Img src={staticFile(FALLBACK_SRC)} />.
export const VIEWBOX = '0 0 100 100';
export const PATHS: string[] = [
  // placeholder mark: a ring with a spark
  'M50 6a44 44 0 1 0 0.01 0Zm0 10a34 34 0 1 1-0.01 0Z',
  'M50 26l6 18 18 6-18 6-6 18-6-18-18-6 18-6Z',
];
export const FALLBACK_SRC = 'site/logo.png';
