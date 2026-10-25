# X 帖子存档：用 Claude/ChatGPT 剪视频的 8 个仓库

- 出处：Brendan Jowett（@jowettbrendan）2026-10-24 帖子，链接 https://x.com/jowettbrendan/status/2113937838563864798
- 归档日期：2026-10-25；归档方式：整仓原件 + 技能库收录 + 云盘正式存档
- 说明：本笔记为归纳记录，不复制帖子原文。

## 清单与存档状态

| 仓库 | Star（2026-10-25 GitHub API 实测） | 许可证 | muse 仓库存档 | 技能库收录 |
|---|---|---|---|---|
| nateherkai/herk-edit-kit（Codex/Claude Code 剪辑工具包：剪静默、审片、故事规划、Hyperframes+GSAP 动效；前身 Hyperframes Student Kit） | 2151 | MIT | herk-edit-kit/（1050 文件，405MB；无单个 >50MB 文件，无排除项） | 15 个 skill（herk-* 前缀，取 .agents/skills  canonical 版；.claude 镜像版仅 4 处脚本路径前缀不同，内容等价未重复收） |
| heygen-com/hyperframes（Claude 用代码构建视频并本地渲染 MP4） | 71613 | Apache-2.0 | hyperframes/（9179 文件含 2 个符号链接，335MB；无排除项） | 已有集成只补缺：此前库里已有 21 个 hyperframes-* skill（旧快照）；本轮补 6 个 agent skill（hyperframes-captions-overlay 等）+ 7 个 registry block（hyperframes-block-* 前缀）；skills/ 下 7 个旧 skill 与库内版本已分叉，按"已有跳过"未覆盖重写 |
| Melvynx/video-agent-skills（免费 Claude Code skills：编剧/剪辑/翻译/发布短视频与长视频） | 49 | MIT | video-agent-skills/（522 文件，13MB） | 13 个 skill（video-agent-* 前缀，含 references/ 的整文件夹复制） |
| browser-use/video-use（Claude 不看视频直接剪辑） | 29753 | MIT | video-use/（36 文件，844KB） | 工具库，仅存档不进技能库 |
| remotion-dev/skills（教 Claude 写可用的 Remotion 视频代码） | 5641 | 未声明（仓内无 LICENSE，README 与 package.json 亦无许可声明） | remotion-skills/（293 文件，3.0MB） | 12 个 skill（remotion-* 原名）；LICENSE 文件按 elsalvatore-video-editor 先例写为"未声明"状态说明（非虚构许可文本），索引 license 标 NOASSERTION |
| Zulko/moviepy（几行代码剪切/拼接/加字幕） | 15031 | MIT | moviepy/（426 文件，96MB） | 工具库，仅存档不进技能库 |
| m-bain/whisperX（精确到每个词的字幕） | 24828 | BSD-2-Clause | whisperX/（35 文件，18MB） | 工具库，仅存档不进技能库 |
| WyattBlue/auto-editor（自动剪掉静音片段） | 5613 | Unlicense | auto-editor/（188 文件，35MB） | 工具库，仅存档不进技能库（其 skills/ 下 4 个 SKILL.md 随整仓存档保留，未单独收录） |

## 技能库变化

- 总数 1308 → 1361（+53：herk 15 + video-agent 13 + remotion 12 + hyperframes agent skill 6 + hyperframes block 7）
- 双落点：drama-factory/src/main/resources/skills-bundled/ 与 skill/ 镜像，_index.json 双登记，rewritten=false，SKILL.md 与上游逐字节一致（抽查核验），唯一例外：herk-motion-showreel 上游 frontmatter 的 description 含未加引号的 `: `（YAML 非法，注册表加载会跳过），按 2026-10-20 既有惯例仅对 frontmatter 做最小修补（description 改双引号转义，正文逐字节不变，解析后描述文本与原文一致），其余 52 个 skill 全逐字节一致
- 注意：herk 与 video-agent 的 skill 正文会引用仓库内其他文件（如 herk 的 style-library、video-agent 的共享脚本），随 skill 文件夹入库后这些跨文件夹引用在库内不解析；与库内既存 268 处悬空引用同类历史遗留，ReferenceIntegrity 测试仅锁定 toonflow 三项，不受影响

## 回复提及（未入库）

- kitcut-hq/kitcut：仅为 @ogamaniuk 在该帖子下的一条回复提及，非作者正文清单；按要求只记入本笔记，**未 clone、未入库、未上云盘**。

## 云盘正式存档

- 位置：Google Drive「02项目/Muse」文件夹（正式存档，非暂存）
- 包名：herk-edit-kit-source-20261025.tar.gz、hyperframes-source-20261025.tar.gz、video-agent-skills-source-20261025.tar.gz、video-use-source-20261025.tar.gz、remotion-skills-source-20261025.tar.gz、moviepy-source-20261025.tar.gz、whisperX-source-20261025.tar.gz、auto-editor-source-20261025.tar.gz（各包为对应存档副本打包，不含 .git）
