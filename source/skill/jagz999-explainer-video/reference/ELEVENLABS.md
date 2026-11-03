# ElevenLabs reference

API key: `ELEVENLABS_API_KEY` (env or `.env`). Header on every call: `xi-api-key: <key>`.
Note: a key may lack the `user_read` scope (so `GET /v1/user` 401s) yet still work for TTS/SFX/music/voices — validate with `GET /v1/voices` instead.

## Text-to-speech with timestamps (for cue sync)
`POST /v1/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128`
Body: `{"text","model_id":"eleven_multilingual_v2","voice_settings":{"stability":0.45,"similarity_boost":0.8,"style":0.0,"use_speaker_boost":true}}`
Returns `{audio_base64, alignment:{characters[], character_start_times_seconds[], character_end_times_seconds[]}}`.
Find a keyword's start time: lowercase-join `characters`, `indexOf(keyword)`, read `character_start_times_seconds[idx]`. That index → cue `at` time.

## Music (separate background track)
`POST /v1/music?output_format=mp3_44100_128`  Body: `{"prompt","music_length_ms"}`.
Returns the audio bytes directly. Good for a full-length bed; keep it understated (mean ~ -19 dB) so narration leads.

## Sound effects (palette for the SFX track)
`POST /v1/sound-generation`  Body: `{"text","duration_seconds","prompt_influence":0.55}`.
- **Minimum `duration_seconds` is 0.5** (shorter → HTTP 400).
- Occasionally returns a **near-silent** clip. ALWAYS check with `ffmpeg -i clip.mp3 -af volumedetect -f null -`; if `max_volume < -30 dB`, regenerate with a clearer/louder prompt.
- Suggested palette: `whoosh` (transitions), `lift` (3D rises), `open` (dropdowns), `click` (Send), `type` (typing), `shimmer` (decrypt), `chip` (attestation ticks), `success` (verified), `logo` (intro/outro sting).

## Voices
`GET /v1/voices` → list. Example narrator used in the reference build: **Eric** `cjVigY5qzO86Huf0OWal` (smooth, trustworthy). Offer the user a few; let them choose.

## Other providers / no key
- **macOS `say`**: `say -v Samantha -o vo.aiff "..."; ffmpeg -i vo.aiff vo.mp3`. No word timestamps → estimate cue times.
- **Bring-your-own (OpenAI/Azure/Google/etc.)**: produce `script.json` + per-scene durations, hand it to the user, wire their returned clips back in.
