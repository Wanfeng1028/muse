# Other providers, accounts and cost

How to direct non-ElevenLabs models and when they win.

Contents
1. Other providers
2. Account and cost

---

## Other providers

How to write a delivery direction anywhere: **who** (persona, age, region), **to whom and where** (scene), **how** (2 to 3
precise emotion words plus delivery: "reassuring, attentive; measured pace; a smile in the voice"), **accent** stated
explicitly, and what not to do phrased positively. Keep it short; long directions leak or average out.

| Provider | Control | Beats ElevenLabs when |
|---|---|---|
| OpenAI `gpt-4o-mini-tts` | free-text `instructions` (affect, tone, pacing, accent) | fast scratch VO and English drafts with no casting step |
| Google Gemini TTS | style prompt (audio profile / scene / director's notes), inline tags, 130+ languages, 2 speakers | long-tail languages, cheap bulk, two-person dialogue |
| Cartesia Sonic-3 | numeric speed (0.6 to 1.5) and volume per line, emotion enum | you need numeric pace per line, or realtime latency |
| Hume Octave | short acting instructions ("speaking to a child") | character acting from a description |
| Fish Audio | emotion markers or bracket tags | cheap cloning, high-volume social |

None were benchmarked here: run the same 3 to 4 lines blind through each candidate.

## Account and cost

- The ElevenLabs free tier can't use library voices or Voice Design through the API and is non-commercial; use Starter or
  higher. Starter allows 3 concurrent requests (multilingual class); use 2. A burst of ~27 parallel requests got an account
  flagged (it recovered on its own).
- The usage counter lags; read the `character-cost` response header per request.
- One take of a 14-line, 73 s script is ~880 characters including tags. Budget 2 to 3× the script length for takes and
  retakes; casting tests cost the most.
