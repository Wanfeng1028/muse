package com.interlude.replay

object AggregateMarkdown {
    fun render(report: AggregateReport): String {
        val sb = StringBuilder()
        sb.append("# 多对局聚合复盘报告\n\n")
        sb.append("- 对局数：").append(report.sessionCount).append('\n')
        sb.append("- 事件总数：").append(report.totalEvents).append('\n')
        sb.append('\n')

        sb.append("## 常用路径 TopN\n\n")
        if (report.topPaths.isEmpty()) {
            sb.append("暂无路径数据。\n")
        } else {
            sb.append("| 路径 | 局数 | 占比 |\n")
            sb.append("| --- | --- | --- |\n")
            for (stat in report.topPaths) {
                sb.append("| ")
                    .append(stat.path.joinToString(" → "))
                    .append(" | ")
                    .append(stat.count)
                    .append(" | ")
                    .append(formatPercent(stat.share))
                    .append(" |\n")
            }
        }
        sb.append('\n')

        sb.append("## 抉择点分布\n\n")
        if (report.choiceDists.isEmpty()) {
            sb.append("暂无抉择点数据。\n")
        } else {
            var currentScene: String? = null
            for (dist in report.choiceDists) {
                if (dist.sceneId != currentScene) {
                    if (currentScene != null) sb.append('\n')
                    currentScene = dist.sceneId
                    sb.append("### ").append(dist.sceneId).append("\n\n")
                    sb.append("| 选项 | 目标 | 选择次数 | 占比 |\n")
                    sb.append("| --- | --- | --- | --- |\n")
                }
                sb.append("| ")
                    .append(dist.label)
                    .append(" | ")
                    .append(dist.target)
                    .append(" | ")
                    .append(dist.picks)
                    .append(" | ")
                    .append(formatPercent(dist.share))
                    .append(" |\n")
            }
        }
        sb.append('\n')

        sb.append("## 流失点聚合\n\n")
        if (report.churnSpots.isEmpty()) {
            sb.append("未发现流失点。\n")
        } else {
            sb.append("| 场景 | 流失局数 | 流失率 |\n")
            sb.append("| --- | --- | --- |\n")
            for (spot in report.churnSpots) {
                sb.append("| ")
                    .append(spot.sceneId)
                    .append(" | ")
                    .append(spot.sessions)
                    .append(" | ")
                    .append(formatPercent(spot.rate))
                    .append(" |\n")
            }
        }

        return sb.toString()
    }

    private fun formatPercent(value: Double): String = String.format("%.1f", value * 100) + "%"
}
