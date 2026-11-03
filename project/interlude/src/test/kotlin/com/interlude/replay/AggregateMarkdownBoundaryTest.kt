package com.interlude.replay

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.*

class AggregateMarkdownBoundaryTest {

    // 事实来源：AggregateAnalyzer.kt `if (sessionCount == 0) { return AggregateReport(sessionCount = 0, totalEvents = 0, topPaths = emptyList(), choiceDists = emptyList(), churnSpots = emptyList()) }`
    @Test
    fun `空 sessions 渲染四个标题与三处占位文本`() {
        val report = AggregateAnalyzer.analyze(emptyList())
        val markdown = AggregateMarkdown.render(report)
        assertTrue(markdown.contains("# 多对局聚合复盘报告"))
        assertTrue(markdown.contains("## 常用路径 TopN"))
        assertTrue(markdown.contains("## 抉择点分布"))
        assertTrue(markdown.contains("## 流失点聚合"))
        assertTrue(markdown.contains("暂无路径数据。"))
        assertTrue(markdown.contains("暂无抉择点数据。"))
        assertTrue(markdown.contains("未发现流失点。"))
        assertTrue(markdown.contains("- 对局数：0"))
        assertTrue(markdown.contains("- 事件总数：0"))
    }

    // 事实来源：AggregateMarkdown.kt `sb.append("| ").append(stat.path.joinToString(" → "))` 与 `private fun formatPercent(value: Double): String = String.format("%.1f", value * 100) + "%"`
    @Test
    fun `单 session 路径占比渲染为 100_0 百分号`() {
        val events = listOf(
            SessionStart("s1", "script.txt", 1, "t0"),
            SceneEnter("scene1", "t1"),
            SceneEnter("scene2", "t2"),
            SessionEnd("win", "p1", "t3")
        )
        val report = AggregateAnalyzer.analyze(listOf(events))
        val markdown = AggregateMarkdown.render(report)
        assertTrue(markdown.contains("scene1 → scene2"))
        assertTrue(markdown.contains("100.0%"))
        assertTrue(markdown.contains("- 对局数：1"))
    }

    // 事实来源：AggregateMarkdown.kt `sb.append("| ").append(dist.label).append(" | ").append(dist.target)` 与 `sb.append("### ").append(dist.sceneId)` 原样拼接不做转义
    @Test
    fun `特殊字符不转义原样输出`() {
        val sceneId = "a*b_c#`e"
        val label = "选*A_项"
        val events = listOf(
            SessionStart("s1", "script.txt", 1, "t0"),
            SceneEnter(sceneId, "t1"),
            ChoiceMade(sceneId, label, "target1", emptyList(), "t2"),
            SessionEnd("win", "p1", "t3")
        )
        val report = AggregateAnalyzer.analyze(listOf(events))
        val markdown = AggregateMarkdown.render(report)
        assertTrue(markdown.contains(sceneId))
        assertTrue(markdown.contains(label))

        val pipeEvents = listOf(
            SessionStart("s2", "script.txt", 1, "t0"),
            SceneEnter("sceneX", "t1"),
            ChoiceMade("sceneX", "A|B", "target2", emptyList(), "t2"),
            SessionEnd("win", "p2", "t3")
        )
        val pipeReport = AggregateAnalyzer.analyze(listOf(pipeEvents))
        val pipeMarkdown = AggregateMarkdown.render(pipeReport)
        assertTrue(pipeMarkdown.contains("A|B"))
    }

    // 事实来源：AggregateAnalyzer.kt `.take(topN)` 与 AggregateMarkdown.kt `if (report.topPaths.isEmpty()) { sb.append("暂无路径数据。\n") }`
    @Test
    fun `topN 等于 0 时路径区显示暂无路径数据`() {
        val sessions = (1..5).map { i ->
            listOf(
                SessionStart("s$i", "script.txt", 1, "t0"),
                SceneEnter("scene$i", "t1"),
                SessionEnd("win", "p$i", "t2")
            )
        }
        val report = AggregateAnalyzer.analyze(sessions, topN = 0)
        assertTrue(report.topPaths.isEmpty())
        val markdown = AggregateMarkdown.render(report)
        assertTrue(markdown.contains("暂无路径数据。"))
    }

    // 事实来源：AggregateAnalyzer.kt `.sortedWith(compareByDescending<PathStat> { it.count }.thenBy { pathSortKey(it.path) }).take(topN)`
    @Test
    fun `topN 为 1 只取排序第一的路径`() {
        val sessions = (1..5).map { i ->
            listOf(
                SessionStart("s$i", "script.txt", 1, "t0"),
                SceneEnter("scene$i", "t1"),
                SessionEnd("win", "p$i", "t2")
            )
        }
        val report = AggregateAnalyzer.analyze(sessions, topN = 1)
        assertEquals(1, report.topPaths.size)
        assertEquals(listOf("scene1"), report.topPaths[0].path)
    }

    // 事实来源：AggregateAnalyzer.kt `.take(topN)` 当 topN 等于路径总数时全取
    @Test
    fun `topN 恰好等于总数时全取`() {
        val sessions = (1..5).map { i ->
            listOf(
                SessionStart("s$i", "script.txt", 1, "t0"),
                SceneEnter("scene$i", "t1"),
                SessionEnd("win", "p$i", "t2")
            )
        }
        val report = AggregateAnalyzer.analyze(sessions, topN = 5)
        assertEquals(5, report.topPaths.size)
        val markdown = AggregateMarkdown.render(report)
        for (i in 1..5) {
            assertTrue(markdown.contains("scene$i"))
        }
    }

    // 事实来源：AggregateAnalyzer.kt `.take(topN)` 当 topN 大于路径总数时取全部
    @Test
    fun `topN 大于总数时全取`() {
        val sessions = (1..5).map { i ->
            listOf(
                SessionStart("s$i", "script.txt", 1, "t0"),
                SceneEnter("scene$i", "t1"),
                SessionEnd("win", "p$i", "t2")
            )
        }
        val report = AggregateAnalyzer.analyze(sessions, topN = 10)
        assertEquals(5, report.topPaths.size)
    }

    // 事实来源：AggregateMarkdown.kt `private fun formatPercent(value: Double): String = String.format("%.1f", value * 100) + "%"` 当 share 为 0.5 时输出 50.0%
    @Test
    fun `两局 share 一半渲染为 50_0 百分号`() {
        val sessions = listOf(
            listOf(
                SessionStart("s1", "script.txt", 1, "t0"),
                SceneEnter("sceneA", "t1"),
                SessionEnd("win", "p1", "t2")
            ),
            listOf(
                SessionStart("s2", "script.txt", 1, "t0"),
                SceneEnter("sceneB", "t1"),
                SessionEnd("win", "p2", "t2")
            )
        )
        val report = AggregateAnalyzer.analyze(sessions)
        val markdown = AggregateMarkdown.render(report)
        assertTrue(markdown.contains("50.0%"))
    }
}
