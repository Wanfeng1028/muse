---
name: kwindla-caption-clip
version: 1.0.0
description: Download a YouTube clip, transcribe it with Deepgram, and burn styled subtitles into the video.
---

# Caption Clip Workflow

Produce a short captioned video from a YouTube URL: pull a specific time range, send the audio through Deepgram for transcription, tidy the transcript, then render styled burned-in subtitles with ffmpeg.

## Requirements

- `yt-dlp` on PATH (for slicing the video by time range)
- `ffmpeg` on PATH (for transcoding and burning subtitles)
- `DEEPGRAM_API_KEY` available in the environment or in a local `.env` file
- Python 3 (to run the bundled JSON→SRT converter)
- A caption-friendly font; the style below prefers Avenir Next Medium and degrades to Arial

## Steps

### 1. Grab the clip section

Use yt-dlp's section downloader to fetch only the part of the video you need. The `*START-END` syntax accepts timestamps.

```bash
yt-dlp --download-sections "*START-END" -o "clip_name.%(ext)s" "YOUTUBE_URL"
```

For example, a clip spanning 02:53 to 04:15:

```bash
yt-dlp --download-sections "*02:53-04:15" -o "clip_intro.%(ext)s" "https://www.youtube.com/watch?v=VIDEO_ID"
```

### 2. Normalize the container

yt-dlp may produce a webm. Transcode to mp4 so downstream steps get a predictable container:

```bash
ffmpeg -i clip_name.webm -y clip_name.mp4
```

### 3. Transcribe via Deepgram

Read the API key from `.env` (stripping surrounding quotes), then POST the media file to Deepgram's listen endpoint with Nova-2, smart formatting, punctuation, and utterance segmentation enabled. Save the raw response as JSON.

```bash
DEEPGRAM_API_KEY=$(grep '^DEEPGRAM_API_KEY=' .env | cut -d'=' -f2 | tr -d '"' | tr -d "'")

curl -s --request POST \
  --url 'https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&punctuate=true&utterances=true' \
  --header "Authorization: Token $DEEPGRAM_API_KEY" \
  --header 'Content-Type: audio/mp4' \
  --data-binary @clip_name.mp4 > clip_transcript.json
```

The `utterances=true` flag is required — the SRT converter consumes the `results.utterances` array.

### 4. Convert JSON to SRT

Run the bundled converter against the Deepgram response:

```bash
python3 scripts/json-to-srt.py clip_transcript.json clip.srt
```

### 5. Clean the subtitles

Open `clip.srt` and write a cleaned copy to `clip_clean.srt`. Apply these edits:

- Correct words the model misheard.
- Drop filler phrases such as "like", "you know", "I'd say", "yeah", "um", "uh", "sort of", "kind of".
- Join very short fragments into full sentences so lines read naturally.
- Reword where spoken phrasing reads awkwardly on screen.
- Sanity-check timestamps (a value like `00:00:60` must be rewritten as `00:01:00`).

### 6. Burn in the captions

Render the cleaned SRT onto the video with a semi-transparent background box:

```bash
ffmpeg -i clip_name.mp4 \
  -vf "subtitles=clip_clean.srt:force_style='FontSize=24,FontName=Avenir Next Medium,PrimaryColour=&H00FFFFFF,BackColour=&H80000000,BorderStyle=4,Outline=0,Shadow=0,MarginV=30,MarginL=40,MarginR=40'" \
  -c:a copy -y clip_captioned.mp4
```

## Style parameters

| Parameter | Value | Meaning |
|-----------|-------|---------|
| FontSize | 24 | Point size |
| FontName | Avenir Next Medium | Clean sans-serif; fall back to Arial |
| PrimaryColour | &H00FFFFFF | White text (`AABBGGRR` hex) |
| BackColour | &H80000000 | Half-transparent black box |
| BorderStyle | 4 | Draws the opaque box using BackColour |
| MarginV | 30 | Distance from bottom edge |
| MarginL / MarginR | 40 | Left and right padding |

## Font alternatives

If Avenir Next Medium isn't installed, these render well for captions: SF Pro Display, Helvetica Neue, Futura, or Arial as a universal fallback. List what's available:

```bash
fc-list : family | sort -u | grep -iE '(avenir|sf pro|helvetica|futura)'
```

## Produced files

| File | Purpose |
|------|---------|
| `clip_name.mp4` | Downloaded source clip |
| `clip_transcript.json` | Raw Deepgram response, kept for re-runs |
| `clip.srt` | Auto-converted subtitles |
| `clip_clean.srt` | Hand-edited subtitles |
| `clip_captioned.mp4` | Final video with burned-in captions |
