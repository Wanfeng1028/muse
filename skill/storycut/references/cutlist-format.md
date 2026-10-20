# Cut-list draft schema

Claude writes JSON like this after reading `transcript.json`:

```json
{
  "title": "A founder's unexpected first customer",
  "audience": "LinkedIn founders",
  "goal": "A truthful 90-second founder story",
  "target_seconds": 90,
  "editor_notes": "The middle may need a title card for context.",
  "clips": [
    {
      "order": 1,
      "title": "The setback",
      "role": "hook",
      "segment_ids": ["s0004", "s0005"],
      "reason": "Introduces stakes immediately",
      "quote": "We almost closed the company."
    },
    {
      "order": 2,
      "title": "A way forward",
      "role": "payoff",
      "segment_ids": ["s0016", "s0017"],
      "reason": "Provides a concrete resolution"
    }
  ]
}
```

Only use `segment_ids` that exist in `transcript.json`; within a clip they must be consecutive in source order. `order` values must be 1, 2, 3, etc. Story order can be different from source order. Quotes must appear verbatim in the clip's transcript (case-insensitive and whitespace-normalized). Avoid repeated source segments between clips.

The validator generates exact `start_seconds`, `end_seconds`, timecodes, and durations from the source segments. Add no invented numbers to the draft. `target_seconds` is a goal; the validator warns if the total diverges significantly.

