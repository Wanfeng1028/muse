# Retrieval and agent navigation

## Short path

Read the `video-router` description, then route a structured request. Read the selected guide and one full catalog record. Retrieve a few relevant upstream skills and inspect their pinned directories. Only then fetch the chosen provider’s current schema. Avoid injecting the entire catalog into a system prompt.

```bash
python3 scripts/avs.py route --task motion --agent astra --engine remotion
python3 scripts/avs.py route --task reference --model h3-max --audio-only
python3 scripts/avs.py route --task retake --model ltx-2-5
python3 scripts/avs.py search 'kinetic typography' --kind skills --limit 5
python3 scripts/avs.py search 'ltx 2.5' --kind models
python3 scripts/avs.py show seedance-2-5-byteplus
```

`route` returns `needs_brief`, `preflight_required` or `no_compatible_route`. Invalid request fields/types return an error and process exit code 2. A valid no-match result is not a process failure; inspect its status. Catalog validation/drift errors exit 1. The router does not execute a selected workflow.

## Structured contract

Use `--request path.json` for reliable constraints. Supported fields include `task`, `model`, `family`, `engine`, `agent`, `host`, `runtime`, `provider`, `require`, `duration`, `fps`, `resolution`, `as_of`, `recent_only`, `available_tools`, reference counts/durations, `audio_only`, `media_local_only`, `budget_usd`, `input_audio_seconds`, `auto_duration` and `limit`. CLI options explicitly supplied override corresponding JSON fields. Natural-language task inference is lexical and labeled as such; it is not a semantic planner. Supply hard constraints explicitly.

Reference images/videos/audio are separate fields. A first-frame asset is not automatically a loose reference. Duration denotes a single generated segment, not the length of a whole edited film. Media-local privacy restricts the media runtime, not whether the controller itself runs in the cloud. Unknown price and numeric constraints remain preflight gaps.

## RAG or external index

`registry/retrieval.jsonl` contains one record per model, engine, controller, skill or workflow. Each has a stable ID, kind, record ID, content hash and serialized record text. Embed or index only changed hashes; retain source URLs, revision, evidence level and snapshot date as metadata. Apply structured capability/provider filters before similarity ranking, not after recommending an incompatible result.

The built-in search uses BM25 lexical scoring and exact-ID boosts without dependencies, embeddings or network access. `registry/navigation.json` offers lane → workflow and family → model/skill navigation. Unsupported capabilities and evidence gaps must remain visible to downstream agents; do not drop them during chunking. The generated standalone router has its own catalog and guides, so copying only its skill directory is sufficient.

Operation limits replace, rather than inherit, the general creation table. For LTX input-audio generation, pass `input_audio_seconds` to distinguish the source length from a requested output length. `auto_duration` is separate from a fixed `duration`; anchor incompatibilities remain hard constraints. Specialized local tasks include `inpaint`, `outpaint`, `restore`, `exr-hdr`, `dub` and `foley`.
