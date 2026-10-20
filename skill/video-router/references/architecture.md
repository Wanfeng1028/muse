# Architecture and curation rules

## Independent axes

The catalog separates controller, host, task, render engine, model family/version, provider surface and skill adapter. A model surface is the smallest approved generation unit. A family can group it, but cannot confer undocumented abilities on a sibling checkpoint or reseller.

`registry/models.json` holds supported and explicitly unsupported capabilities, release-date provenance, operation IDs, coupled output profiles, evidence and preflight notes. `engines.json` holds deterministic toolchains, while `agents.json` holds controller preferences. `skills.json` links inspected upstream paths at immutable revisions, with file hashes, license observations, provider scope, portability and review level. `workflows.json` defines staged actions and failure transitions.

## Why recent-first is not newest-wins

The preference window is six **calendar months** ending at the requested `as_of` date. Hard constraints are evaluated before recency. Unknown dates receive no recency boost; repository updates and checkpoint filename suffixes are not release dates. Provider availability and early access are labeled separately. The initial snapshot uses April 1–October 1, 2026.

Older LTX retake/extension routes and Kling remain discoverable when appropriate. Rendering engines are not penalized for being established: a recent video model does not replace the need for precise code-rendered typography. Routing scores are documented heuristics, not quality benchmarks or measured cost rankings.

## Evidence is not certification

Primary model/provider documentation supports capabilities. Upstream `SKILL.md` inspection supports the existence and stated purpose of a skill. Community discussions and directories help discover candidates and failure modes. They do not prove API compatibility, commercial rights, security or output quality. `runtime_tested: false` is intentional throughout upstream/model records.

The catalog distinguishes `content-reviewed` from `path-and-metadata-inspected`. The latter means the path, frontmatter and revision were retrieved, not that every instruction/script was deeply audited. Repository license and skill-declared license are recorded separately. Missing or ambiguous licensing prevents vendoring, not linking.

## Canonical and generated files

Edit the JSON registries and authored Markdown guides. `scripts/build.py` derives model/skill indexes, individual skill cards, navigation, JSONL retrieval chunks and standalone skill packages. `--check` detects drift. Third-party skill bodies, weights and binaries are not copied into the repository. The bundled router contains this project’s own metadata, guides and offline code.

The router never installs packages, reads credentials, invokes generation APIs or publishes media. Platform-bound skills are withheld from recommendations unless their declared prerequisites are supplied, and provider mismatches are filtered. Unknown numeric constraints are explicitly left for preflight; verified violations are rejected. A compatible route always remains `preflight_required`.

## Boundaries

This is a source-backed starting collection, not an exhaustive inventory of the internet. Models without a sufficiently checked surface remain discovery-only through their upstream skills or the research watchlist. Refreshing a repository SHA alone must never certify a changed API or update a model release date. A maintainer reviews semantic changes before promoting a route.
