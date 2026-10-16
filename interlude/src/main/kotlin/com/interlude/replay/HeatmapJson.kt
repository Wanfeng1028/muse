package com.interlude.replay

import java.util.Locale

object HeatmapJson {

    fun render(report: HeatmapReport): String {
        val sb = StringBuilder()
        sb.append("{\"sessions\":").append(report.sessionCount)
        sb.append(",\"total_choices\":").append(report.totalChoices)
        sb.append(",\"nodes\":[")
        appendNodes(sb, report.nodes)
        sb.append("],\"churn_points\":[")
        appendNodes(sb, report.churnPoints)
        sb.append("],\"top_paths\":[")
        for ((idx, hp) in report.topPaths.withIndex()) {
            if (idx > 0) sb.append(',')
            sb.append("{\"path\":[")
            for ((pi, nid) in hp.path.withIndex()) {
                if (pi > 0) sb.append(',')
                sb.append('"').append(escape(nid)).append('"')
            }
            sb.append("],\"count\":").append(hp.count).append('}')
        }
        sb.append("]}")
        return sb.toString()
    }

    private fun appendNodes(sb: StringBuilder, nodes: List<HeatNode>) {
        for ((idx, n) in nodes.withIndex()) {
            if (idx > 0) sb.append(',')
            sb.append("{\"node_id\":\"").append(escape(n.nodeId)).append('"')
            sb.append(",\"scene_id\":\"").append(escape(n.sceneId)).append('"')
            sb.append(",\"label\":\"").append(escape(n.label)).append('"')
            sb.append(",\"visits\":").append(n.visits)
            sb.append(",\"drops\":").append(n.drops)
            sb.append(",\"drop_rate\":")
                .append(String.format(Locale.US, "%.4f", n.dropRate))
            sb.append('}')
        }
    }

    private fun escape(s: String): String {
        val sb = StringBuilder(s.length + 8)
        for (c in s) {
            when (c) {
                '"' -> sb.append("\\\"")
                '\\' -> sb.append("\\\\")
                '\b' -> sb.append("\\b")
                '\u000C' -> sb.append("\\f")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                else -> {
                    if (c < '\u0020') {
                        sb.append(String.format(Locale.US, "\\u%04x", c.code))
                    } else {
                        sb.append(c)
                    }
                }
            }
        }
        return sb.toString()
    }
}
