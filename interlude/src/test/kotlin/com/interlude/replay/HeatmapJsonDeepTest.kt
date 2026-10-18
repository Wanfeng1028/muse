package com.interlude.replay

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class HeatmapJsonDeepTest {

    private fun node(
        nodeId: String = "n1",
        sceneId: String = "s1",
        label: String = "label",
        visits: Int = 0,
        drops: Int = 0,
        dropRate: Double = 0.0
    ): HeatNode = HeatNode(
        nodeId = nodeId,
        sceneId = sceneId,
        label = label,
        visits = visits,
        drops = drops,
        dropRate = dropRate
    )

    private fun report(
        sessionCount: Int = 0,
        totalChoices: Int = 0,
        nodes: List<HeatNode> = emptyList(),
        churnPoints: List<HeatNode> = emptyList(),
        topPaths: List<HotPath> = emptyList()
    ): HeatmapReport = HeatmapReport(
        sessionCount = sessionCount,
        totalChoices = totalChoices,
        nodes = nodes,
        churnPoints = churnPoints,
        topPaths = topPaths
    )

    @Test
    fun `render empty report`() {
        val out = HeatmapJson.render(report())
        assertEquals(
            "{\"sessions\":0,\"total_choices\":0,\"nodes\":[],\"churn_points\":[],\"top_paths\":[]}",
            out
        )
    }

    @Test
    fun `render node fields`() {
        val out = HeatmapJson.render(
            report(
                sessionCount = 1,
                totalChoices = 10,
                nodes = listOf(
                    node(
                        nodeId = "n1",
                        sceneId = "s1",
                        label = "开始",
                        visits = 10,
                        drops = 3,
                        dropRate = 0.3
                    )
                )
            )
        )
        assertTrue(out.contains("\"node_id\":\"n1\""), out)
        assertTrue(out.contains("\"scene_id\":\"s1\""), out)
        assertTrue(out.contains("\"visits\":10"), out)
        assertTrue(out.contains("\"drops\":3"), out)
        assertTrue(out.contains("\"drop_rate\":0.3000"), out)
    }

    @Test
    fun `drop rate four decimals`() {
        val out = HeatmapJson.render(
            report(
                nodes = listOf(node(nodeId = "n1", dropRate = 1.0 / 3.0))
            )
        )
        assertTrue(out.contains("\"drop_rate\":0.3333"), out)
    }

    @Test
    fun `churn points rendered separately`() {
        val out = HeatmapJson.render(
            report(
                nodes = emptyList(),
                churnPoints = listOf(node(nodeId = "c1"))
            )
        )
        assertTrue(out.contains("\"churn_points\":[{"), out)
        assertTrue(out.contains("\"nodes\":[]"), out)
    }

    @Test
    fun `top paths rendered`() {
        val out = HeatmapJson.render(
            report(
                topPaths = listOf(HotPath(path = listOf("a", "b", "c"), count = 7))
            )
        )
        assertTrue(out.contains("\"path\":[\"a\",\"b\",\"c\"]"), out)
        assertTrue(out.contains("\"count\":7"), out)
    }

    @Test
    fun `escapes quotes in label`() {
        val out = HeatmapJson.render(
            report(nodes = listOf(node(label = "a\"b")))
        )
        assertTrue(out.contains("\"label\":\"a\\\"b\""), out)
    }

    @Test
    fun `escapes newline in node id`() {
        val out = HeatmapJson.render(
            report(nodes = listOf(node(nodeId = "x\ny")))
        )
        assertTrue(out.contains("\"node_id\":\"x\\ny\""), out)
    }

    @Test
    fun `multiple nodes comma separated`() {
        val out = HeatmapJson.render(
            report(
                nodes = listOf(
                    node(nodeId = "n1"),
                    node(nodeId = "n2")
                )
            )
        )
        val occurrences = Regex(Regex.escape("},{\"node_id\"")).findAll(out).count()
        assertEquals(1, occurrences, out)
    }
}
