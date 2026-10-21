# App Icon Provenance

The macOS application icon is One Memory product artwork approved for the
Tencent open-source release.

- Source component: 128 x 128, corner radius 28.
- Exported SVG canvas: 164 x 172, including the authored drop shadow.
- Copyright and trademark ownership remain with Tencent and the One Memory
  project; Apache-2.0 does not grant additional trademark rights.

`app-icon-source.svg` is the checked-in vector reference. The build consumes
`app-icon-source.png`, the approved high-resolution bitmap, so macOS does not
first rasterize the 164 x 172 SVG canvas at low resolution. Run
`node scripts/build_app_icon.cjs` to regenerate `icon.png` and `icon.icns`.
Do not reconstruct the icon from the old `memory-mark.svg`; that produces a
different mark from the approved product artwork.
