# OpenAgents Round 12: Message Reactions

## 1. Original spec (OpenAgents messaging mod)
Based on the OpenAgents messaging mod README and its adapter.py/mod.py as actually shipped:
- Reactions are a closed set of exactly 8 string values: "+1", "like", "smile", "ok", "done", "heart", "thumbs_up", "thumbs_down".
- Clients send `thread.reaction.add` and `thread.reaction.remove` events.
- Adding a reaction is idempotent; a duplicate add is treated as a no-op.
- Removing a reaction that does not exist is a no-op.
- Summaries count agents per reaction type and completely omit empty types.
- Reactions are listed alongside message data, showing counts only in list views.

## 2. This round's design decisions
- This is a TypeScript re-implementation for botstalk, not a direct code port, because OpenAgents is written in Python and botstalk relies on TypeScript and native WebSockets.
- Reactions are stored in their own `message_reactions` table (columns: `message_id`, `room`, `reactor`, `reaction`, `created_at_ms`) with a UNIQUE constraint on `message_id + reactor + reaction`, instead of being embedded directly in the message payload.
- The HTTP layer, not the storage layer, is responsible for validating reaction types.
- Add and remove operations are idempotent at the HTTP layer: a duplicate add returns `added: false` with HTTP 200, and a duplicate remove returns `removed: false` with HTTP 200.
- Reactions endpoints do not require room membership beyond the message existing in that room, remaining consistent with the unauthenticated history endpoint.
- The Web UI for reactions is explicitly NOT included in this round; this iteration covers backend, tests, and smoke scripts only.

## 3. Delivery file list
- `gateway/src/reactions.ts` (new)
- `gateway/src/server.ts` (reactions routes + import)
- `gateway/test/reactions.test.ts` (new)
- `scripts/smoke-reactions.mjs` (new)

## 4. Acceptance
- Unit/Integration tests passed: 983
- New reactions tests passed: 19
- Smoke script steps passed: 12

## 5. Known limitations
- Reactions are not broadcast over WebSocket yet; viewers must re-fetch history or call the reactions endpoint to see updates.
- There is no toggle endpoint; clients must compose the toggle logic themselves using GET combined with POST/DELETE.
- The reactions list exposes reactor IDs to anyone who can call the endpoint, sharing the same visibility as message senders in the history endpoint.
