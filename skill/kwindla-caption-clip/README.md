# Caption YouTube Clips

Download YouTube video clips with timestamps, transcribe with [Deepgram](https://deepgram.com), and burn styled captions.

## What it does

1. Downloads a specific section of a YouTube video using yt-dlp
2. Transcribes audio using Deepgram's Nova-2 model
3. Generates SRT subtitles from the transcript
4. **Cleans up the transcript using Claude** - fixes errors, removes filler words, improves readability
5. Burns styled captions onto the video with ffmpeg

## Example output

```
clip_captioned.mp4 - Final video with burned-in captions
```

Captions appear with white text on a semi-transparent black background, positioned at the bottom of the video.

## Prerequisites

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTube downloader
- [ffmpeg](https://ffmpeg.org/) - Video processing
- [Deepgram API key](https://console.deepgram.com/) - Set as `DEEPGRAM_API_KEY` in `.env` or environment

Install on macOS:
```bash
brew install yt-dlp ffmpeg
```

## Usage

### With Claude Code

This was designed as a [Claude Code skill](https://docs.anthropic.com/en/docs/claude-code). To use it:

1. Install [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
2. Copy the skill to your Claude skills directory:
   ```bash
   cp -r . ~/.claude/skills/caption-clip
   ```
3. Create a `.env` file with your Deepgram API key:
   ```bash
   echo "DEEPGRAM_API_KEY=your_key_here" > .env
   ```
4. Ask Claude: "Caption this YouTube video from 2:53 to 4:15: https://youtube.com/watch?v=VIDEO_ID"

Claude will handle the entire workflow and clean up the auto-generated transcript.

## Transcript cleanup (LLM-in-the-loop)

The key advantage of using this as a Claude Code skill is the transcript cleanup step. After generating the initial SRT, Claude reads it and creates a cleaned version (`clip_clean.srt`) by:

- **Fixing transcription errors** - Corrects misheard words based on context
- **Removing filler words** - Deletes "like", "you know", "um", "uh", "sort of", "kind of", "I'd say", "yeah"
- **Consolidating fragments** - Merges short utterances into complete sentences
- **Improving readability** - Adjusts phrasing to flow better when read vs. heard
- **Fixing timestamps** - Corrects invalid times (e.g., `00:00:60` → `00:01:00`)

This step uses Claude's judgment - there's no script for it. The result is captions that read naturally rather than a literal transcription of speech patterns.

### Manual usage

#### Step 1: Download clip

```bash
yt-dlp --download-sections "*02:53-04:15" -o "clip.%(ext)s" "https://youtube.com/watch?v=VIDEO_ID"
```

#### Step 2: Convert to MP4

```bash
ffmpeg -i clip.webm -y clip.mp4
```

#### Step 3: Transcribe with Deepgram

```bash
curl -s --request POST \
  --url 'https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&punctuate=true&utterances=true' \
  --header "Authorization: Token $DEEPGRAM_API_KEY" \
  --header 'Content-Type: audio/mp4' \
  --data-binary @clip.mp4 > transcript.json
```

#### Step 4: Generate SRT

```bash
python3 scripts/json-to-srt.py transcript.json clip.srt
```

#### Step 5: Clean up transcript (manual)

Edit `clip.srt` to fix errors and improve readability. Save as `clip_clean.srt`.

#### Step 6: Burn captions

```bash
ffmpeg -i clip.mp4 \
  -vf "subtitles=clip_clean.srt:force_style='FontSize=24,FontName=Avenir Next Medium,PrimaryColour=&H00FFFFFF,BackColour=&H80000000,BorderStyle=4,Outline=0,Shadow=0,MarginV=30,MarginL=40,MarginR=40'" \
  -c:a copy -y clip_captioned.mp4
```

## Caption styling

| Parameter | Value | Description |
|-----------|-------|-------------|
| FontSize | 24 | Point size |
| FontName | Avenir Next Medium | Clean sans-serif |
| PrimaryColour | &H00FFFFFF | White text |
| BackColour | &H80000000 | 50% transparent black |
| BorderStyle | 4 | Opaque box background |
| MarginV | 30 | Pixels from bottom |

Colors use AABBGGRR format (alpha, blue, green, red).

## Alternative fonts

If Avenir Next is unavailable:
- SF Pro Display
- Helvetica Neue
- Futura
- Arial (universal fallback)

Check available fonts:
```bash
fc-list : family | sort -u | grep -iE '(avenir|sf pro|helvetica|futura)'
```

## Output files

| File | Description |
|------|-------------|
| `clip.mp4` | Downloaded clip |
| `transcript.json` | Raw Deepgram response |
| `clip.srt` | Auto-generated subtitles |
| `clip_clean.srt` | Cleaned subtitles (if edited) |
| `clip_captioned.mp4` | Final video with captions |

## Technical notes

- Deepgram's `utterances=true` parameter groups words into natural speech segments
- The `smart_format=true` parameter adds punctuation and formatting
- SRT timestamps use comma as decimal separator (not period)
- ffmpeg's subtitle filter requires escaping special characters in paths

## License

MIT
