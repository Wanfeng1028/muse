package com.interlude.lint

object Report {

    fun formatText(issues: List<Issue>): String {
        val errors = issues.count { it.severity == Severity.ERROR }
        val warnings = issues.count { it.severity == Severity.WARNING }
        val sb = StringBuilder()
        sb.append("issues: ").append(issues.size)
            .append(" (errors: ").append(errors)
            .append(", warnings: ").append(warnings)
            .append(")")
        for (issue in issues) {
            sb.append('\n')
            sb.append('[').append(issue.severity.name).append("] ")
                .append(issue.code).append(' ')
                .append(issue.sceneId).append(':').append(issue.line).append(' ')
                .append(issue.message)
        }
        return sb.toString()
    }

    fun formatJson(issues: List<Issue>): String {
        val errors = issues.count { it.severity == Severity.ERROR }
        val warnings = issues.count { it.severity == Severity.WARNING }
        val sb = StringBuilder()
        sb.append("{\"summary\":{\"issues\":").append(issues.size)
            .append(",\"errors\":").append(errors)
            .append(",\"warnings\":").append(warnings)
            .append("},\"issues\":[")
        for ((i, issue) in issues.withIndex()) {
            if (i > 0) sb.append(',')
            sb.append("{\"severity\":\"").append(escape(issue.severity.name))
                .append("\",\"code\":\"").append(escape(issue.code))
                .append("\",\"scene\":\"").append(escape(issue.sceneId))
                .append("\",\"line\":").append(issue.line)
                .append(",\"message\":\"").append(escape(issue.message))
                .append("\"}")
        }
        sb.append("]}")
        return sb.toString()
    }

    private fun escape(s: String): String {
        val sb = StringBuilder(s.length)
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
                    if (c < ' ') {
                        sb.append("\\u")
                        val hex = c.code.toString(16)
                        repeat(4 - hex.length) { sb.append('0') }
                        sb.append(hex)
                    } else {
                        sb.append(c)
                    }
                }
            }
        }
        return sb.toString()
    }
}
