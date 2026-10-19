# Skills 审计报告（2026-10-19）

审计员：W3-drama
日期：2026-10-19

## 一、范围与方法

本次审计覆盖 `drama-factory/src/main/resources/skills-bundled/` 下的 35 个 skills，其中 17 个为内置、18 个来自社区，均为此前两轮收录所得。

审计采用三种方法：

1. **机械扫描脚本**：解析 frontmatter、检查 SKILL.md 内引用的 examples/scripts/assets 路径是否存在、检查 LICENSE 文件是否存在、扫描 TODO/FIXME/待补充/占位符等标记、校验 `_index.json` 一致性。共发现 61 项。
2. **dpsk 内容质量审查**：分 3 批对 SKILL.md 做内容质量审查，关注空洞、占位、名实不符三类问题。
3. **上游核验**：对 agamm/video-agent 的 `video_agent.py` 子命令逐一核对，并从 GitHub 上游抓取 LICENSE 进行比对。

## 二、发现与修复

以下问题均已落地修复，尚未提交。

| 编号 | 问题 | 影响 | 修复状态 |
| --- | --- | --- | --- |
| 1 | 30 个 skill 目录缺 LICENSE 文件 | 许可证合规缺口，其中 video-shots/video-sync/video-scrub 3 个为 Apache-2.0，触及 Apache-2.0 第 4 条合规要求 | 已从各上游仓库原样抓取补齐 26 个（含上述 3 个 Apache-2.0）；剩余 4 个（watzing-video-editor、jordantobyll-video-edit、jordantobyll-pan-3d-transition、openmontage-video-edit）为 `rewritten:true`，属独立重写、无原文复制，按政策不需携带上游 LICENSE，`_index.json` 已有 `rewritten:true` + `sourceUrl` + `rewriteNote` |
| 2 | 26 个 SKILL.md frontmatter 缺 version | `SkillInstallService` 用 `descriptor.getVersion()` 做安装版本 pin，空版本会使版本校验形同虚设 | 已补 `version: 1.0.0` |
| 3 | frontmatter name 重名：video-editor-ffmpeg 与 video-editor-remotion 的 name 均为 `video-editor` | 两个 skill 无法按 name 区分，与目录 id 不一致 | 已分别改为 `video-editor-ffmpeg` / `video-editor-remotion`，与目录 id 一致 |
| 4 | `_index.json` schema 不统一：26 个条目仅有 id/license/source 三键 | 索引信息不完整，与 SKILL.md 无法对齐 | 已补齐为全键（name/version/description/author），与各 SKILL.md frontmatter 逐字一致（含 YAML folded `>` 描述的正确展开） |
| 5 | 5 处"引用路径在 skill 目录内不存在" | 经判定全部为说明性引用，非实际缺失 | 不改文件：video-explainer 的 4 处（SKILL.md 第 46 行已明说这些 scripts/ 路径相对上游 claude-video-kit 仓库根目录）；jordantobyll-pan-3d-transition 的 `scripts/video_effects/public/montage/`（"把你的航拍素材放到这里"的用户操作指引）；video-toolkit 的 `tools/*.py`（文档明示 toolkit 在 `~/.openclaw/workspace/claude-code-video-toolkit` 外部固定路径） |

## 三、误报驳回清单

以下 dpsk 报告项经人工核验后驳回，不属问题：

- 6 个 agamm/video-agent 系 skill 的 `uv run video-agent <子命令>`：已下载上游 `video_agent.py`（93KB）逐一核对，info/transcribe/speech-segments/position-grid/captions/reframe/frame/edl/tighten/beats/snap 全部真实存在。
- video-editing 的 `scripts/trim.sh`、claude-video-skill 的 `scripts/contact_sheet.py`、watzing-video-editor 的 `build_editor.py`：文件均真实存在。
- jordantobyll-pan-3d-transition 的"pip install remotion"：SKILL.md 全文零处出现 `pip`，系误报。
- shorts 的"名实不符"判词前后矛盾、editor 引用 cutting-rhythm（同批 skill）误报：驳回。

## 四、编造与事故诚实记录

### 4.1 dpsk 编造记录

`_index.json` 富化时，dpsk 给 creating-video/drawing-video/parsing-video/processing-video/autoshorts 编造了版本号（0.2.1/1.0.1/0.4.0/0.1.2/2.0.0），原文 frontmatter 根本没有 version。已按"缺 version 填 1.0.0"规则纠正。

### 4.2 编排事故记录

`apply_dpsk2.py` 对 OLD 做子串/前缀匹配：video-editor-ffmpeg 与 video-editor-remotion 在改名后，version 批次的 OLD（`name: video-editor`）命中了已改名行（`name: video-editor-ffmpeg`）的前缀，导致两文件 frontmatter 损坏（name 回退、version 重复行、`1.0.0-ffmpeg` 伪版本）。

已手工精确修复两文件，并对 35 个 SKILL.md frontmatter 与 `_index.json` 做了全量一致性复核（name/version 逐一比对），现已全部一致。

教训：OLD 绝不能是目标行改名后的前缀；应用后必须 `git diff` 逐行检查。

## 五、遗留与建议

- **video-toolkit 的 frontmatter name 为 `video_toolkit`（下划线）**，与目录 id（video-toolkit，连字符）不一致。`metadata.openclaw.skillKey` 用的是连字符版。建议后续统一为连字符，本轮未动，以免影响外部引用。
- **MIT LICENSE 均为上游原文**（含各自 copyright holder），未改写。
