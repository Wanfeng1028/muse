# File Schemas

These schemas describe useful shapes from the Conteto Machino work. They are defaults, not rigid requirements. Add fields freely when a future workflow needs them.

## Timeline CSV

Recommended columns:

- `segment`: zero-based segment index
- `timeline_start`: start time within the rendered edit, in seconds
- `abs_start`: optional source-song time, in seconds
- `duration`: segment duration, in seconds
- `kind`: source role, such as `gameplay`, `crowd`, `real_laser`, `photos_nature`, `character_select`
- `source_tag`: human-readable source pool name
- `source_file`: path or URL to source media
- `source_start`: start time inside the source clip
- `priority`: musical priority, usually `1-5`
- `motion_score`: source-window score used by the picker
- `speed`: playback speed multiplier
- `note`: optional creative or QA note

Minimum useful columns:

- `segment`
- `timeline_start`
- `duration`
- `kind`
- `source_tag`
- `source_start`

## Brief JSON

Recommended fields:

```json
{
  "name": "Edit name",
  "slug": "edit_slug",
  "mood": "One-sentence creative direction",
  "final_video": "outputs/edit.mp4",
  "format": "vertical 9:16",
  "resolution": "1080x1920",
  "song_start": 52.98,
  "song_end": 88.17,
  "target_duration": 35.19,
  "segment_count": 84,
  "source_mix": {},
  "kind_mix": {},
  "timeline": "outputs/edit_timeline.csv",
  "contact_sheet": "outputs/edit_contact_sheet.jpg",
  "generated_visuals": false,
  "notes": []
}
```

## Config JSON

For future builders, prefer a config that can change without editing script logic:

```json
{
  "audio": "source_audio/song.mp3",
  "cut_markers": "outputs/song_cut_markers_30fps.csv",
  "target_window": {"start": 52.98, "end": 88.17},
  "format": {"width": 1080, "height": 1920, "fps": 30},
  "sources": [
    {"tag": "Ultimate Spikes", "kind": "gameplay", "glob": "media/spikes*.mp4", "weight": 7}
  ],
  "edit_variants": [
    {
      "name": "KO Storm",
      "slug": "ko_storm",
      "seed": 4101,
      "source_bias": {"Ultimate Spikes": 3},
      "accent_slots": {"real_laser": [0, 8, 39], "crowd": [17, 41]},
      "layout": {"foreground_y": 630, "foreground_scale": 1080}
    }
  ]
}
```

Use this as a shape to borrow from, not a schema validator.
