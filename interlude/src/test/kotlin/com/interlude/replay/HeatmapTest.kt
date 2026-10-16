package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class HeatmapTest {

    private fun choice(sceneId: String, label: String, target: String, at: String): ChoiceMade =
        ChoiceMade(sceneId, label, target, emptyList(), at)

    private fun scene(sceneId: String, at: String): SceneEnter = SceneEnter(sceneId, at)

    private fun end(outcome: String, at: String): SessionEnd = SessionEnd(outcome, null, at)

    @Test
    fun emptySessions() {
        val report = HeatmapAnalyzer.analyze(emptyList())
        assertEquals(0, report.sessionCount)
        assertEquals(0, report.totalChoices)
        assertTrue(report.nodes.isEmpty())
        assertTrue(report.churnPoints.isEmpty())
        assertTrue(report.topPaths.isEmpty())
    }

    @Test
    fun singlePathNoDrops() {
        val events = listOf(
            scene("s1", "t1"),
            choice("s1", "A", "s2", "t2"),
            scene("s2", "t3"),
            choice("s2", "B", "s3", "t4"),
            scene("s3", "t5"),
        )
        val report = HeatmapAnalyzer.analyzeSession(events)
        assertEquals(2, report.nodes.size)
        val a = report.nodes.first { it.nodeId == "s1::A" }
        val b = report.nodes.first { it.nodeId == "s2::B" }
        assertEquals(1, a.visits)
        assertEquals(0, a.drops)
        assertEquals(1, b.visits)
        assertEquals(0, b.drops)
    }

    @Test
    fun loopVisitsTwice() {
        val events = listOf(
            scene("s1", "t1"),
            choice("s1", "A", "s2", "t2"),
            scene("s2", "t3"),
            choice("s2", "B", "s1", "t4"),
            scene("s1", "t5"),
            choice("s1", "A", "s2", "t6"),
            scene("s2", "t7"),
        )
        val report = HeatmapAnalyzer.analyzeSession(events)
        val a = report.nodes.first { it.nodeId == "s1::A" }
        assertEquals(2, a.visits)
    }

    @Test
    fun dropDetectedAfterSessionEnd() {
        val events = listOf(
            scene("s1", "t1"),
            choice("s1", "A", "s2", "t2"),
            end("done", "t3"),
        )
        val report = HeatmapAnalyzer.analyzeSession(events)
        val a = report.nodes.first { it.nodeId == "s1::A" }
        assertEquals(1, a.drops)
        assertEquals(1.0, a.dropRate)
    }

    @Test
    fun aggregateAcrossSessions() {
        fun one(): List<SessionEvent> = listOf(
            scene("s1", "t1"),
            choice("s1", "A", "s2", "t2"),
            scene("s2", "t3"),
        )
        val report = HeatmapAnalyzer.analyze(listOf(one(), one(), one()))
        val a = report.nodes.first { it.nodeId == "s1::A" }
        assertEquals(3, a.visits)
        assertEquals(3, report.totalChoices)
    }

    @Test
    fun churnThresholdRespected() {
        val lowVisits = listOf(
            scene("s1", "t1"),
            choice("s1", "A", "s2", "t2"),
            end("done", "t3"),
        )
        val report1 = HeatmapAnalyzer.analyzeSession(lowVisits)
        val a1 = report1.nodes.first { it.nodeId == "s1::A" }
        assertEquals(1.0, a1.dropRate)
        assertEquals(1, a1.visits)
        assertTrue(report1.churnPoints.none { it.nodeId == "s1::A" })

        fun droppedSession(tag: String): List<SessionEvent> = listOf(
            scene("s1", "t$tag-1"),
            choice("s1", "A", "s2", "t$tag-2"),
            end("done", "t$tag-3"),
        )
        val report2 = HeatmapAnalyzer.analyze(listOf(droppedSession("a"), droppedSession("b")))
        val a2 = report2.nodes.first { it.nodeId == "s1::A" }
        assertEquals(2, a2.visits)
        assertEquals(1.0, a2.dropRate)
        assertTrue(report2.churnPoints.any { it.nodeId == "s1::A" })
    }

    @Test
    fun topPathsIdenticalSequences() {
        fun one(): List<SessionEvent> = listOf(
            scene("s1", "t1"),
            choice("s1", "A", "s2", "t2"),
            scene("s2", "t3"),
            choice("s2", "B", "s3", "t4"),
            scene("s3", "t5"),
        )
        val report = HeatmapAnalyzer.analyze(listOf(one(), one()))
        assertEquals(1, report.topPaths.size)
        assertEquals(2, report.topPaths.first().count)
        assertEquals(listOf("s1::A", "s2::B"), report.topPaths.first().path)
    }

    @Test
    fun jsonRenderContainsFieldsAndFourDecimalRate() {
        fun droppedSession(tag: String): List<SessionEvent> = listOf(
            scene("s1", "t$tag-1"),
            choice("s1", "A", "s2", "t$tag-2"),
            end("done", "t$tag-3"),
        )
        val report = HeatmapAnalyzer.analyze(listOf(droppedSession("a"), droppedSession("b")))
        val json = HeatmapJson.render(report)
        assertTrue(json.contains("\"node_id\""))
        assertTrue(json.contains("\"visits\""))
        assertTrue(json.contains("\"drop_rate\""))
        assertTrue(json.contains("\"drop_rate\":1.0000"))
    }
}
