# Errors and privacy

## Recovery

- `review-result.json is missing`: run the review command.
- `script changed after review`: review the edited script again.
- `review status is fix/block`: resolve the listed checks; do not render.
- `No TTS backend available`: use supported macOS demo mode or configure a provider separately.
- Remotion browser launch fails: rerun outside a restrictive process sandbox; do not disable system security controls.
- Verification fails: keep the MP4 local, fix the script or visual rhythm, review again, and rerender.

## Privacy boundary

- Keep briefs, scripts, receipts, narration, and MP4 files local by default.
- Never print or copy API-key values. Doctor reports only configured/not configured.
- Never bundle `.env`, voice samples, tokens, account cookies, local absolute paths, or private task state.
- Do not upload, publish, deploy, sign in, create an account, or call a paid service from this skill without separate user authorization.
- The canonical demo uses repository-owned text and generated shapes only.
