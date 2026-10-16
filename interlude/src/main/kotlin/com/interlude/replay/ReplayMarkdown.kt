package com.interlude.replay

object ReplayMarkdown {
    /** 把复盘报告渲染为 Markdown 文本。 */
    fun render(report: ReplayReport): String {
        val sb = StringBuilder()
        sb.append("# 复盘报告\n\n")
        sb.append("- 对局：`${report.sessionId}`\n")
        sb.append("- 剧本：`${report.scriptFile}`\n")
        sb.append("- 开始时间：${report.startedAt}\n")
        sb.append("- 结束时间：${report.endedAt ?: "未记录"}\n")
        sb.append("- 事件总数：${report.timeline.size}\n\n")

        // 时间线
        sb.append("## 对局时间线\n\n")
        if (report.timeline.isEmpty()) {
            sb.append("本局无事件记录。\n\n")
        } else {
            report.timeline.forEachIndexed { index, event ->
                val line = when (event) {
                    is SessionStart -> "对局开始（${event.playerCount} 人）"
                    is SceneEnter -> "进入场景 ${event.sceneId}"
                    is ChoiceMade -> "在 ${event.sceneId} 选择「${event.label}」→ ${event.target}"
                    is VoteCast -> "第 ${event.round} 轮：${event.voter} 投票给 ${event.target}"
                    is Elimination -> "${event.player} 出局（${event.reason}）"
                    is KeyMoment -> {
                        if (event.sceneId != null) {
                            "标注：${event.note}（场景 ${event.sceneId}）"
                        } else {
                            "标注：${event.note}"
                        }
                    }
                    is SessionEnd -> "对局结束：${event.outcome}"
                }
                sb.append("${index + 1}. $line\n")
            }
            sb.append("\n")
        }

        // 抉择点复盘
        sb.append("## 抉择点复盘\n\n")
        if (report.decisionPoints.isEmpty()) {
            sb.append("本局没有记录到抉择点。\n\n")
        } else {
            report.decisionPoints.forEachIndexed { index, dp ->
                sb.append("### ${index + 1}. ${dp.sceneId}（第 ${dp.sceneLine} 行）\n\n")
                if (dp.sceneText.isNotEmpty()) {
                    sb.append("> ${dp.sceneText}\n\n")
                }
                sb.append("选择了：${dp.chosenLabel} → ${dp.chosenTarget}\n\n")
                sb.append("没走的路：\n")
                dp.alternatives.forEach { alt ->
                    sb.append("- ${alt.label} → ${alt.target}\n")
                }
                sb.append("\n")
            }
        }

        // 投票与出局
        sb.append("## 投票与出局\n\n")
        if (report.voteRounds.isEmpty()) {
            sb.append("本局无投票记录。\n\n")
        } else {
            report.voteRounds.forEach { round ->
                sb.append("### 第 ${round.round} 轮\n\n")
                round.votes.forEach { v ->
                    sb.append("- ${v.voter} → ${v.target}\n")
                }
                round.eliminated?.let { e ->
                    sb.append("\n出局：${e.player}（${e.reason}）\n")
                }
                sb.append("\n")
            }
        }

        // MVP 评选
        sb.append("## MVP 评选\n\n")
        if (report.playerStats.isEmpty()) {
            sb.append("本局无玩家投票数据，MVP 评选略。\n\n")
        } else {
            sb.append("| 玩家 | 投出 | 被投 | 出局轮次 | 你的 MVP 一票 |\n")
            sb.append("| --- | --- | --- | --- | --- |\n")
            report.playerStats.forEach { ps ->
                val elimRound = ps.eliminatedRound?.toString() ?: "-"
                sb.append("| ${ps.player} | ${ps.votesCast} | ${ps.votesReceived} | $elimRound |  |\n")
            }
            sb.append("\n")
        }

        // 关键标注
        sb.append("## 关键标注\n\n")
        if (report.keyMoments.isEmpty()) {
            sb.append("无。\n\n")
        } else {
            report.keyMoments.forEach { km ->
                sb.append("- ${km.at} ${km.note}\n")
            }
            sb.append("\n")
        }

        // 对局结果
        sb.append("## 对局结果\n\n")
        sb.append("结果：${report.outcome ?: "未记录"}\n")
        report.winner?.let { w ->
            sb.append("胜者：$w\n")
        }
        sb.append("\n")

        // 数据问题
        if (report.warnings.isNotEmpty()) {
            sb.append("## 数据问题\n\n")
            report.warnings.forEach { w ->
                sb.append("- $w\n")
            }
            sb.append("\n")
        }

        return sb.toString()
    }
}