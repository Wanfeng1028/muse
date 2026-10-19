package com.interlude.replay

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.*

class AggregateAnalyzerTest {

    // 事实来源：AggregateAnalyzer.kt `fun analyze(sessions: List<List<SessionEvent>>, topN: Int = 10): AggregateReport`
    @Test
    fun `空输入不抛异常且各列表为空`() {
        val report = AggregateAnalyzer.analyze(emptyList())
        assertEquals(0, report.sessionCount)
        assertEquals(0, report.totalEvents)
        assertTrue(report.topPaths.isEmpty())
        assertTrue(report.choiceDists.isEmpty())
        assertTrue(report.churnSpots.isEmpty())
    }

    // 事实来源：AggregateAnalyzer.kt `share = count / sessionCount`
    @Test
    fun `两局相同路径合并计数与 share`() {
        val s1 = listOf(
            SessionStart("s1", "a.json", 3, "t0"),
            SceneEnter("scene1", "t1"),
            SceneEnter("scene2", "t2"),
            SessionEnd("win", "p1", "t9")
        )
        val s2 = listOf(
            SessionStart("s2", "a.json", 3, "t0"),
            SceneEnter("scene1", "t1"),
            SceneEnter("scene2", "t2"),
            SessionEnd("lose", null, "t9")
        )
        val report = AggregateAnalyzer.analyze(listOf(s1, s2))
        assertEquals(2, report.sessionCount)
        assertEquals(1, report.topPaths.size)
        val stat = report.topPaths[0]
        assertEquals(listOf("scene1", "scene2"), stat.path)
        assertEquals(2, stat.count)
        assertEquals(1.0, stat.share, 1e-9)
    }

    // 事实来源：AggregateAnalyzer.kt `path 为该局 SceneEnter 的 sceneId 序列（去连续重复）`
    @Test
    fun `路径去连续重复`() {
        val s1 = listOf(
            SessionStart("s1", "a.json", 3, "t0"),
            SceneEnter("scene1", "t1"),
            SceneEnter("scene1", "t2"),
            SceneEnter("scene2", "t3"),
            SceneEnter("scene2", "t4"),
            SceneEnter("scene1", "t5"),
            SessionEnd("win", "p1", "t9")
        )
        val report = AggregateAnalyzer.analyze(listOf(s1))
        assertEquals(1, report.topPaths.size)
        assertEquals(listOf("scene1", "scene2", "scene1"), report.topPaths[0].path)
    }

    // 事实来源：AggregateAnalyzer.kt `share = picks / 该 sceneId 下总 picks`
    @Test
    fun `抉择点分布 share 在同一 sceneId 内求和为 1`() {
        val s1 = listOf(
            SessionStart("s1", "a.json", 3, "t0"),
            ChoiceMade("scene1", "A", "tA", emptyList(), "t1"),
            ChoiceMade("scene1", "B", "tB", emptyList(), "t2"),
            ChoiceMade("scene1", "A", "tA", emptyList(), "t3"),
            SessionEnd("win", "p1", "t9")
        )
        val s2 = listOf(
            SessionStart("s2", "a.json", 3, "t0"),
            ChoiceMade("scene1", "B", "tB", emptyList(), "t1"),
            SessionEnd("lose", null, "t9")
        )
        val report = AggregateAnalyzer.analyze(listOf(s1, s2))
        val scene1Dists = report.choiceDists.filter { it.sceneId == "scene1" }
        assertEquals(2, scene1Dists.size)
        val total = scene1Dists.sumOf { it.share }
        assertEquals(1.0, total, 1e-9)
        // s1: A x2, B x1；s2: B x1 → A:2, B:2；picks 相同按 label 升序，A 在前，B 在后
        assertEquals("A", scene1Dists[0].label)
        assertEquals(2, scene1Dists[0].picks)
        assertEquals("B", scene1Dists[1].label)
        assertEquals(2, scene1Dists[1].picks)
    }

    // 事实来源：AggregateAnalyzer.kt `一局若无 SessionEnd 事件，取其最后一个 SceneEnter 或 ChoiceMade 的 sceneId 记一次流失`
    @Test
    fun `无 SessionEnd 的局记流失点 有 SessionEnd 的不记`() {
        val s1 = listOf(
            SessionStart("s1", "a.json", 3, "t0"),
            SceneEnter("scene1", "t1"),
            SceneEnter("scene2", "t2")
        )
        val s2 = listOf(
            SessionStart("s2", "a.json", 3, "t0"),
            SceneEnter("scene1", "t1"),
            ChoiceMade("sceneX", "A", "tA", emptyList(), "t2")
        )
        val s3 = listOf(
            SessionStart("s3", "a.json", 3, "t0"),
            SceneEnter("scene1", "t1"),
            SessionEnd("win", "p1", "t9")
        )
        val report = AggregateAnalyzer.analyze(listOf(s1, s2, s3))
        assertEquals(2, report.churnSpots.size)
        val spotMap = report.churnSpots.associateBy { it.sceneId }
        assertEquals(1, spotMap["scene2"]?.sessions)
        assertEquals(1, spotMap["sceneX"]?.sessions)
        assertNull(spotMap["scene1"])
    }

    // 事实来源：AggregateAnalyzer.kt `topPaths 按 count 降序取前 topN`
    @Test
    fun `topN 截断`() {
        val sessions = (1..5).map { i ->
            listOf(
                SessionStart("s$i", "a.json", 3, "t0"),
                SceneEnter("scene$i", "t1"),
                SessionEnd("win", "p1", "t9")
            )
        }
        val report = AggregateAnalyzer.analyze(sessions, topN = 3)
        assertEquals(3, report.topPaths.size)
    }

    // 事实来源：AggregateMarkdown.kt `# 多对局聚合复盘报告` / `## 常用路径 TopN` / `## 抉择点分布` / `## 流失点聚合`
    @Test
    fun `AggregateMarkdown 含四个标题段`() {
        val s1 = listOf(
            SessionStart("s1", "a.json", 3, "t0"),
            SceneEnter("scene1", "t1"),
            SceneEnter("scene2", "t2"),
            ChoiceMade("scene1", "A", "tA", emptyList(), "t3"),
            SessionEnd("win", "p1", "t9")
        )
        val report = AggregateAnalyzer.analyze(listOf(s1))
        val md = AggregateMarkdown.render(report)
        assertTrue(md.contains("# 多对局聚合复盘报告"))
        assertTrue(md.contains("## 常用路径 TopN"))
        assertTrue(md.contains("## 抉择点分布"))
        assertTrue(md.contains("## 流失点聚合"))
    }

    // 事实来源：AggregateMarkdown.kt `路径用 `a → b → c` 连接`
    @Test
    fun `AggregateMarkdown 表格行含箭头`() {
        val s1 = listOf(
            SessionStart("s1", "a.json", 3, "t0"),
            SceneEnter("scene1", "t1"),
            SceneEnter("scene2", "t2"),
            SessionEnd("win", "p1", "t9")
        )
        val report = AggregateAnalyzer.analyze(listOf(s1))
        val md = AggregateMarkdown.render(report)
        assertTrue(md.contains("scene1 → scene2"))
    }

    // 事实来源：AggregateMarkdown.kt `无数据时写"暂无路径数据。"` / `无数据写"未发现流失点。"`
    @Test
    fun `AggregateMarkdown 空报告显示占位文本`() {
        val report = AggregateAnalyzer.analyze(emptyList())
        val md = AggregateMarkdown.render(report)
        assertTrue(md.contains("暂无路径数据。"))
        assertTrue(md.contains("未发现流失点。"))
    }
}
