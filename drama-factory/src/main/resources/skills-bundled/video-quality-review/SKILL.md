---
name: video-quality-review
description: "Review generated or code-rendered video through actual playback, audio, content, rights and encoded-file checks."
compatibility: File-reading agents; actual generation requires the separately verified provider or renderer.
metadata:
  version: "1.0.0"
  snapshot: "2026-10-01"
---

# Quality-Review workflow

Read [the playbook](references/guide.md), then [the scoped records](references/records.json). Select the exact backend, version and operation before writing a request.

Record inputs, rights, duration, output constraints and budget. Inspect the live provider schema or renderer dependencies. Treat unknown capabilities as unresolved; never infer them from a related checkpoint or service. Generate only after authorization, preserve job/project provenance, and review actual playback and encoded metadata before delivery.

This is an original routing playbook, not a bundled third-party runtime. Upstream skills and their licenses must be reviewed separately.
