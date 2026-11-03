# X 帖子存档：短剧 Skill 选型实测（程序员鱼皮 @yupi996，2026-10-20）

原帖：https://x.com/yupi996/status/2112416270142652848（本笔记为转述存档，非原文转载）

## 帖子要点

鱼皮介绍开源清单 **UnderleveledBuilder/awesome-short-drama-skills**：收录 83 个短剧/漫剧 Skill。作者做了一轮实测：挑 10 个写剧本的 Skill，与不装 Skill 的 Claude Code 做同一道题（写一部 60 集竖屏短剧，交付分集大纲 + 前 3 集剧本，不给题材），各跑 3 次，AI 盲评。结果：单比剧本，有 5 个 Skill 三次全胜裸机。

清单自带一个选型 Skill，装上后可让 AI 帮挑：`npx skills add UnderleveledBuilder/awesome-short-drama-skills`。

## 实测发现（据帖子附图转述）

- 裸机一集通常写到第八场、超 2 分钟；装了 Skill 的大多收在一到五场（更符合竖屏短剧节奏）。
- 模板感越重的未必越强，"不那么像 Skill"的反而表现好。
- 33 份稿子里 15 份都出现了一个叫"小满"的角色——换哪个 Skill 都躲不掉，疑似模型先验污染，写剧本时要留意。

## 三次全胜的 5 个写剧本 Skill（选型表摘要）

| Skill | 擅长（据附图） |
|---|---|
| jenstory-ai/drama-skills | 台本规范化、细节、分集完善 |
| ShanWan/ai-shortfilm-screenwriting-master | 分镜分场规范、镜头多、对白细致 |
| dyd88/screenwriting-skills | 结构完整、看点密集、人物少 |
| Hao0220/short-drama | 特征性人物、设定完整 |
| adooo111/emma-screenwriting-skills | 日常化描写细腻、情感真挚 |

注：实测仅用 Opus 5.5 一个模型；附图小字为识读转述，个别措辞未逐字核对。

## 仓库结构（已 clone 至 ~/workspace/short-drama-skills-repo）

- 仓库本体许可证 CC0 1.0；83 个 Skill 本身不在仓库内，仓库是目录型：data/ 里有 skills.toml / skill_index.json 等索引（指向各源仓库），evals/ 是评测代码与运行记录。
- 仓库自带唯一 vendored skill：skills/short-drama-skill-finder（选型助手）。
- 集成动作：83 个源仓库按索引逐个 clone、原件收进剧坊官方 skill 库（已派代理执行，含去重与逐仓许可证记录）；finder skill 一并收录。
