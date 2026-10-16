package com.interlude.replay

import java.util.Locale

/**
 * 将热力报告渲染为人类可读的中文文本报告。
 */
object HeatmapText {
    fun render(report: HeatmapReport): String {
        val sb = StringBuilder()
        sb.append("# 路径热力报告\n\n")
        sb.append("- 对局数：").append(report.sessionCount).append('\n')
        sb.append("- 选择事件总数：").append(report.totalChoices).append('\n')
        sb.append('\n')

        sb.append("## Top 热门路径\n\n")
        if (report.topPaths.isEmpty()) {
            sb.append("本批日志中没有记录到选择路径。\n")
        } else {
            sb.append("| 排名 | 路径 | 对局数 |\n")
            sb.append("| --- | --- | --- |\n")
            report.topPaths.forEachIndexed { index, hotPath ->
                sb.append("| ").append(index + 1).append(" | ")
                    .append(hotPath.path.joinToString(" → "))
                    .append(" | ").append(hotPath.count).append(" |\n")
            }
        }
        sb.append('\n')

        sb.append("## Top 流失点\n\n")
        if (report.churnPoints.isEmpty()) {
            sb.append("暂无达到阈值的流失点。\n")
        } else {
            sb.append("| 节点 | 场景 | 选项 | 访问 | 流失 | 流失率 |\n")
            sb.append("| --- | --- | --- | --- | --- | --- |\n")
            report.churnPoints.forEach { node ->
                sb.append("| ").append(node.nodeId)
                    .append(" | ").append(node.sceneId)
                    .append(" | ").append(node.label)
                    .append(" | ").append(node.visits)
                    .append(" | ").append(node.drops)
                    .append(" | ").append(formatRate(node.dropRate))
                    .append(" |\n")
            }
        }
        sb.append('\n')

        sb.append("## 节点热力全表\n\n")
        if (report.nodes.isEmpty()) {
            sb.append("暂无数据。\n")
        } else {
            sb.append("| 节点 ID | 访问 | 流失 | 流失率 |\n")
            sb.append("| --- | --- | --- | --- |\n")
            report.nodes.forEach { node ->
                sb.append("| ").append(node.nodeId)
                    .append(" | ").append(node.visits)
                    .append(" | ").append(node.drops)
                    .append(" | ").append(formatRate(node.dropRate))
                    .append(" |\n")
            }
        }

        return sb.toString()
    }

    private fun formatRate(rate: Double): String =
        String.format(Locale.US, "%.2f%%", rate * 100)
}
