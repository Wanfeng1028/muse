---
name: video-editor
description: |
  Edits, processes, and renders videos using FFmpeg and Remotion. Handles video stitching, transitions, captions, teasers, and transcription.

  USE THIS SKILL WHEN:
  - User mentions video, clip, footage, mp4, mov, avi, mkv, or any video format
  - User wants to combine, stitch, concatenate, merge, or join video files
  - User asks about transitions, fades, crossfades, or effects between clips
  - User needs captions, subtitles, TikTok-style captions, or word highlighting
  - User wants a teaser, trailer, highlight reel, or short preview from longer video
  - User mentions FFmpeg, ffprobe, or any ffmpeg command or error
  - User mentions Remotion, OffthreadVideo, TransitionSeries, or any Remotion error
  - User asks about video transcription, whisper, speech-to-text for video
  - User encounters "inputRange must be strictly monotonically increasing" error
  - User encounters "delayRender was called but not continued" error
  - User sees any video encoding, codec, or rendering error
  - User asks about video duration, resolution, fps, frame rate, or video analysis
  - User asks how to trim, cut, or extract portions of video
  - User has .mp4, .mov, .captions.json files or video folders
  - User is confused about video processing implementation
  - Any error occurs in a video-editor project directory
  - User asks about thumbnails, graphics, overlays, or visual assets for video
  - User needs to generate images or graphics for video content
  - User mentions title cards, lower thirds, end screens, or chapter graphics
---

## Intelligent Editing Workflow

This skill enables Claude to act as a smart video editor. Before executing commands:

1. **Analyze** - Examine videos (duration, resolution, audio) using ffprobe
2. **Transcribe** - Get speech content for smart cuts (if needed)
3. **Ask** - Clarify user intent and preferences
4. **Plan** - Propose edit approach for approval
5. **QA Test** - Run automated tests before user preview (see [rules/qa-testing.md](rules/qa-testing.md))
6. **Preview** - Only show to user after QA passes
7. **Iterate** - Refine based on feedback

See [rules/intelligent-editing.md](rules/intelligent-editing.md) for detailed workflow, questions to ask, and quality checks.

## Tool Selection

| Task | FFmpeg | Remotion |
|------|--------|----------|
| **Stitching** | Same codec, no effects | Transitions, overlays, programmatic |
| **Transitions** | Simple crossfades | Multiple types, custom timing |
| **Captions** | SRT burn-in | TikTok-style word highlighting |
| **Teasers** | Quick clips | Text overlays, branded elements |

**General guidance:**
- **FFmpeg**: Fast CLI operations, batch processing, format conversion
- **Remotion**: Styled content, animations, preview before render, React components

## Rules

### Intelligence Layer
- [rules/intelligent-editing.md](rules/intelligent-editing.md) - Smart editing workflow, questions, quality checks
- [rules/video-analysis.md](rules/video-analysis.md) - Analyze videos with ffprobe
- [rules/transcription.md](rules/transcription.md) - Whisper transcription for speech analysis
- [rules/qa-testing.md](rules/qa-testing.md) - **QA tests before user preview**

### Core Editing
- [rules/stitching.md](rules/stitching.md) - Combine multiple clips into one video
- [rules/transitions.md](rules/transitions.md) - Add fade, slide, wipe between clips
- [rules/captions.md](rules/captions.md) - Add subtitles and TikTok-style captions
- [rules/teasers.md](rules/teasers.md) - Create 30-second teasers/trailers
- [rules/title-cards.md](rules/title-cards.md) - Add chapter headers, bumpers, section titles
- [rules/graphics-generation.md](rules/graphics-generation.md) - Generate thumbnails, overlays, social graphics

### Reference
- [rules/ffmpeg-basics.md](rules/ffmpeg-basics.md) - Common FFmpeg patterns and troubleshooting
- [rules/remotion-setup.md](rules/remotion-setup.md) - Remotion project setup and workflow
- [rules/remotion-tips.md](rules/remotion-tips.md) - Animations, timing, springs, sequences, and captions
- [rules/reference-implementation.md](rules/reference-implementation.md) - **Complete working code to recreate the project**

## Quick Start

### Transcription (Fast)
```bash
# 1. Setup whisper.cpp (one-time)
npx ts-node scripts/setup-whisper.ts

# 2. Transcribe all videos (GPU accelerated)
npx ts-node scripts/transcribe-fast.ts
```

### FFmpeg (CLI)
```bash
# Check installation
which ffmpeg || brew install ffmpeg

# Basic concat (same codec)
ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4

# Burn in subtitles
ffmpeg -i video.mp4 -vf "subtitles=captions.srt" output.mp4
```

### Remotion (React)
```bash
# Start preview (always do this first)
npm run dev

# Render (only when user requests)
npx remotion render CompositionName out/video.mp4
```

## Key Lessons Learned

### Transcription (IMPORTANT)
- **Use `@remotion/install-whisper-cpp`** - NOT Python whisper (10x faster with GPU)
- Use `base.en` model for speed, `medium.en` for final quality
- **Required parameter**: `whisperCppVersion: '1.5.5'` in transcribe() call
- Enable `tokenLevelTimestamps: true` for word-level captions
- Whisper.cpp uses Metal GPU on Mac - 8.5min video in ~85 seconds

### Teasers
- **Never start clips with**: "But", "And", "So", "Now", "It", "This", "That", "They"
- Each clip must have an **explicit subject** - not pronouns or references
- Aim for 3-4 clips totaling 25-30 seconds
- **Playback speed**: 1.3x for energy (1.5x is too fast)
- **Transitions**: Smooth fade (0.4s) between clips
- **First clip**: Must NOT overlap with intro start (avoid repetition)

### Captions
- **Active word**: Yellow `#FFD700`
- **Spoken words**: White `#FFFFFF`
- **Upcoming words**: Light gray `#E0E0E0`
- **Font**: Roboto at 48px for 1080p
- **Black stroke outline** (works on ANY background):
  ```css
  WebkitTextStroke: '3px black',
  paintOrder: 'stroke fill',
  textShadow: '0px 0px 4px rgba(0,0,0,1), 0px 0px 8px rgba(0,0,0,0.8)'
  ```

### Remotion Video Trimming
- Use `OffthreadVideo` component
- Set BOTH `startFrom` AND `endAt` props
- Convert ms to frames: `Math.round((ms / 1000) * fps)`

---

## Edge Cases & Gotchas

### File Naming
- Avoid spaces in video filenames: use `intro.mp4` not `Intro Video.mp4`
- Remotion Folder names can only contain letters, numbers, and hyphens

### Ports
- Remotion Studio may start on port 3001 if 3000 is in use

### Codec Mismatch
- FFmpeg concat demuxer (`-c copy`) fails silently with mismatched codecs
- Use `ffprobe` to check codecs before concatenating
- Use filter_complex for different codecs/resolutions

### Workflow
- **Always preview in Remotion Studio before rendering**
- Never render automatically - wait for user approval
- Copy videos to `public/` folder for Remotion projects
