/** The S1 cubic-bezier(.32,.72,0,1), evaluated for a Three.js property. */
export function graphEase(progress: number): number {
  const t = Math.max(0, Math.min(1, progress));
  if (t === 0 || t === 1) return t;
  let low = 0,
    high = 1;
  for (let i = 0; i < 18; i++) {
    const u = (low + high) / 2;
    const x = 3 * (1 - u) ** 2 * u * 0.32 + u ** 3;
    if (x < t) low = u;
    else high = u;
  }
  const u = (low + high) / 2;
  return 3 * (1 - u) ** 2 * u * 0.72 + 3 * (1 - u) * u ** 2 + u ** 3;
}
