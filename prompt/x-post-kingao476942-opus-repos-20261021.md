# X 帖子存档索引：Kin 的 Opus 5.5 视频仓库清单

- 出处：Kin（@kingao476942），2026-10-21
- 链接：https://x.com/kingao476942/status/2112729924943634602
- 内容概要：该帖推荐了一批用 Claude Opus 5.5 以提示词驱动代码生成视频的 GitHub 仓库（爆款合集、风格技能包、完整 MV 工程、MG 动效与手绘动画起步包等）。用户指令"抄➕存"，8 个仓库已按下表存入本仓库 prompt/ 目录（star 数为 2026-10-21 存档时 GitHub API 实测）。

| 仓库 | Star | 许可证 | 存档状态 |
|---|---|---|---|
| yihui-dev/awesome-opus5-5-videos | 7479 | MIT | 新存：`prompt/awesome-opus5-5-videos/`（707 文件，整仓原件） |
| lemomo-ai/lemo-opuscar | 4565 | MIT | 新存：`prompt/lemo-opuscar/`（2099 文件，整仓原件）；其 skill 本体此前已在剧坊官方技能库（id `lemo-opuscar`，自包含插件版），本轮复核补登记 sourceUrl 与 rewritten=false，技能库总数仍 1282，SkillRegistry 相关测试 26/26 绿 |
| mexicat/pdoom-video | 3039 | MIT | 新存：`prompt/pdoom-video-mexicat/`（154 文件；因与 JohnHeibel 的 PDoomVideo 存档目录同名，加 -mexicat 后缀区分） |
| JohnHeibel/PDoomVideo | 2344 | 未声明（仓内无 LICENSE 文件） | 已存跳过：`prompt/pdoom-video/`（26 文件，此前已存且完整） |
| Vincentwei1021/mg-styles-15 | 1482 | MIT | 新存：`prompt/mg-styles-15/`（384 文件，整仓原件，含全部演示视频） |
| JohnHeibel/ClaudeAnimationBase | 1367 | MIT | 新存：`prompt/claudeanimationbase/`（18 文件，整仓原件） |
| athemeroy/awesome-claude-5-5-videos | 592 | CC BY 4.0 | 新存：`prompt/awesome-claude-5-5-videos/`（322 文件，整仓原件） |
| joeseesun/opus-video-prompts | 550 | 未声明（仓内无 LICENSE 文件） | 已存跳过：`prompt/opus-video-prompts/`（20 文件，此前已存且完整） |

备注：

- 2026-10-24 复核（yihui-dev/awesome-opus5-5-videos）：存档在位且与上游逐字节一致（707 文件 sha256 全对）；上游自 2026-10-13 后无新提交，**无增量**（star 7479 → 9919，为热度增长、内容未变）；云盘存档已补：`awesome-opus5-5-videos-source-20261024.tar.gz`（Google Drive「02项目/Muse」，回查确认）。
- 大文件规则（单个 >50MB 不入库、留 EXCLUDED-MEDIA.md 清单）：本批 6 个新仓均无单个超过 50MB 的文件（最大的为 mg-styles-15 的演示视频，约 38MB），故全部完整复制，无排除项。
- mg-styles-15 本地 clone 位于 ~/workspace/mg-styles-15（因仓库体积大、网络慢，采用 --depth 1 浅克隆，工作树文件完整；其余 5 仓为完整克隆，位于 ~/workspace/ 下同名目录）。
- lemo-opuscar 仓内 plugin/skills/lemo-opuscar/SKILL.md 是"运行时拉取库"的版本，与技能库里已收录的"自包含插件版"同源同名、内容组织不同；技能库不重复收录，本轮只补全索引登记。
