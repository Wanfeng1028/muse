"""Markdown smoothness table from measure_motion.mjs output (one slow eased zoom).
Usage: python3 smooth_table.py <measure_output.txt> <title> > smoothness.md
The measured columns come from the RENDERED pixels (block matching plus RANSAC), the plan
columns from the camera file: a smooth zoom has a measured step that rises and falls with the
plan (no repeated or skipped steps, no stair steps), and a cumulative scale that tracks the plan.
Works for a push in or a pull out. Exit 0 smooth, 3 when a frame steps against the plan's direction
or a per frame step is off the plan by 0.005 or more."""
import json, sys
rows = json.loads(open(sys.argv[1]).read().strip().splitlines()[-1])
print(f"# Smoothness, {sys.argv[2]}\n")
print("| Frame | t (s) | Plan scale | Measured cumulative scale | Plan step | Measured step | Plan dx px | Measured dx | Plan dy px | Measured dy | RANSAC inliers |")
print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
for r in rows:
    print(f"| {r['frame']} | {r['t']:.3f} | {r['plan_scale']:.4f} | {r['meas_cum_scale']:.4f} | {r['plan_step_s']:.5f} | {r['meas_step_s']:.5f} | "
          f"{r['plan_tx']:.2f} | {r['meas_tx']:.2f} | {r['plan_ty']:.2f} | {r['meas_ty']:.2f} | {r['inliers']} |")
st = [r for r in rows if abs(r["plan_step_s"] - 1) > 1e-4]
err = max(abs(r["meas_step_s"] - r["plan_step_s"]) for r in st) if st else 0
cum = max(abs(r["meas_cum_scale"] - r["plan_scale"]) for r in rows)
# monotonic in the plan's own direction: a push in grows every frame, a pull out shrinks every frame
# (the last frames of an ease move less than the block matcher's ~3e-4 noise, so judge only the
# frames that move at least 0.1% and let the step error cover the rest)
mono = all((r["meas_step_s"] - 1) * (r["plan_step_s"] - 1) > 0 for r in st if abs(r["plan_step_s"] - 1) >= 1e-3)
print(f"\nMoving frames: {len(st)}. Largest per frame step error {err:.5f}; largest cumulative scale error {cum:.4f}; "
      f"measured scale never steps against the planned direction: {mono}.")
sys.exit(0 if mono and err < 0.005 else 3)
