# Active skill catalog

This is the maintained routing index for the `video-skill` workspace. Select by the user's requested output and model, not by the repository name. Paths below resolve within this library; an independently installed router may instead resolve the same skill names from the host's available skills.

| Skill / entrypoint | Category | Use when | Deliverable and boundary |
|---|---|---|---|
| [ai-video-production](../SKILL.md) | Production coordination | The request spans stages or asks which production skill applies | Chooses and coordinates relevant skills; does not impose a model, Blender workflow or automatic generation |
| [video-ad-analyzer](../../video-ad-analyzer/SKILL.md) | Ad reference analysis and **video** recreation planning | Analyze viral ads/Reels/Shorts/UGC or adapt their dialogue/action relationships for a new product, character or script | Evidence timeline/JSON, optional local WhisperX draft and alignment, semantic plan and Seedance prompt. Hands Seedance 2.5 syntax to `sd25-pe`; Blender is optional for spatial/motion problems. No video generation or editing |
| [video-scrub](../../video-scrub/SKILL.md) | Local video metadata cleanup | Inspect identifying metadata or clean a local MP4/MOV before sharing; 메타데이터 삭제, 영상 익명화 | Cleaned **video file** plus text/JSON verification of known residues. Independent Node.js/FFmpeg workflow; normal processing path is SDR H.264. No shot/speech analysis, generation, upload or watermark-removal guarantee; see its codec/HDR/caption limits |
| [blender-previs-to-video](../../blender-previs-to-video/SKILL.md) | Previs and result analysis | Build/revise Blender blocking for video references, analyze shot motion, or diagnose generated-video fidelity | Reference analysis, primitive scene/render, comparison or handoff as requested; calls a model writer only when prompt work is needed |
| [sd25-pe](../../sd25-pe/SKILL.md) | **Video** prompt: Seedance 2.5 | SD/Seedance scene prompts, references, previs, keyframes, editing or extension prompts | Model-specific copyable text and reference roles; no service operation |
| [h3-prompt-writing](../../h3-prompt-writing/SKILL.md) | **Video** prompt: MiniMax H3 | H3 text/keyframe modes or full image/video/audio reference prompts | Mode-specific fields, native subject/media labels and retention relationships; no service operation |
| [wan3-prompt-writing](../../wan3-prompt-writing/SKILL.md) | **Video** prompt: Wan 3.0 | Wan text-to-video, image-to-video, references, sound or multi-shot prompts | Wan prompt and applicable reference identifiers; no service operation |
| [gpt-image-25](../../gpt-image-25/SKILL.md) | **Still image**: GPT Image 2.5 | Image-generation/edit prompts, product sheets, backgrounds, keyframes, visible text or reference image edits | Still-image prompt/settings; actual image work only when requested and supported by available tools. Never a video writer |

`SD` means Seedance only when the conversation establishes that meaning. In another context it may refer to a different model; resolve a material ambiguity rather than silently routing it. `H3` here means MiniMax H3, not every product offered by a similarly named platform.

## Choose only the needed route

| User request | Route |
|---|---|
| “이 바이럴 광고의 빠른 컷과 한국어 대사를 분석해줘” | `video-ad-analyzer`; speech workflow only when audio evidence is needed and the runtime is available |
| “이 영상의 위치·기기 정보를 지우고 검증해줘” | `video-scrub`; inspect first, preserve the original and follow the codec/HDR/caption limits; independent of analysis and model writers |
| “제품과 멘트를 바꿔 대사에 맞는 Seedance 영상을 위한 프롬프트를 써줘” | `video-ad-analyzer` for evidence and new dialogue/action relationships, then `sd25-pe` for Seedance 2.5 prompt syntax; no automatic generation |
| “SD로 이 프리비즈를 활용할 프롬프트를 써줘” | `sd25-pe`; inspect relevant motion/reference roles, no automatic Blender rebuild |
| “엄지·검지로 네모를 만드는 다음 장면을 Blender로 만들어줘” | `blender-previs-to-video`; model choice can wait |
| “손이 왜 이렇게 나왔는지 생성 결과를 비교해줘” | `blender-previs-to-video` analysis stage; diagnose before selecting a fix |
| “제품 앞·뒷면만 있는 이미지 시트용 프롬프트” | `gpt-image-25`; still-image task |
| “이 제품 사진으로 Wan 영상을 만들 프롬프트” | `wan3-prompt-writing`; not the still-image writer |
| “H3에서 참조 매핑 후 Subject/Video를 어떻게 쓰지?” | `h3-prompt-writing`, relevant native syntax/reference guide |
| “같은 프리비즈를 SD, H3, Wan용으로 각각 작성해줘” | Shared reference-role brief, then each of the three requested video writers |
| “모델은 나중에 정하고 우선 프리비즈부터” | Blender workflow; do not block on model selection |

## Distribution and supporting files

Production routing and installation use the eight active skill directories above. Keep them as siblings to preserve the relative links in this catalog. Copy each complete folder, including its supporting resources; copying only `SKILL.md` is insufficient. A router installed alone can use skills available by the same identifiers through the host, but does not include their capabilities itself. `video-scrub` can be distributed and used alone; keep its bundled license and source notes with it.

`README.md` is the human entrypoint and setup guide. Root `AGENTS.md` provides workspace instructions. A selected skill's `references/` holds conditional working guidance; `references/sources.md` holds attribution and scope. None of these imply that every file should be loaded for every request.

Project media, runtime environments and model weights are also not bundled. Use the current project's paths for inputs and results. For transcription, reuse a prepared shared or project-specific runtime and cache as described in the analyzer's speech guide; prepare a new environment only when needed.

When adding a skill, update this catalog with its exact identifier, entrypoint, output medium, trigger, deliverable and important overlap. Preserve model-specific syntax in the individual skill; do not maintain a second copy here.
