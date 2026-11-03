package com.interlude.replay

/**
 * 选择节点热力数据。
 *
 * @param nodeId 聚合键，形如 "sceneId::label"
 * @param sceneId 抉择发生的场景 ID
 * @param label 选项文本
 * @param visits 该节点在全部对局中的出现次数
 * @param drops 该节点发生流失的次数（选完不再推进剧情）
 * @param dropRate 流失率 = drops / visits
 */
data class HeatNode(
    val nodeId: String,
    val sceneId: String,
    val label: String,
    val visits: Int,
    val drops: Int,
    val dropRate: Double,
)

/**
 * 热门路径：一份对局的选项序列（按 ChoiceMade 顺序的 nodeId 列表）。
 *
 * @param path nodeId 序列
 * @param count 完全相同的路径序列出现次数
 */
data class HotPath(val path: List<String>, val count: Int)

/**
 * 热力分析报告。
 */
data class HeatmapReport(
    val sessionCount: Int,
    val totalChoices: Int,
    val nodes: List<HeatNode>,
    val churnPoints: List<HeatNode>,
    val topPaths: List<HotPath>,
)

object HeatmapAnalyzer {

    fun analyze(
        sessions: List<List<SessionEvent>>,
        dropThreshold: Double = 0.5,
        minVisits: Int = 2,
        topPathLimit: Int = 5,
    ): HeatmapReport {
        data class Agg(var sceneId: String, var label: String, var visits: Int, var drops: Int)

        val agg = LinkedHashMap<String, Agg>()
        val pathCounts = LinkedHashMap<List<String>, Int>()
        var totalChoices = 0

        for (events in sessions) {
            val path = ArrayList<String>()
            for (i in events.indices) {
                val e = events[i]
                if (e is ChoiceMade) {
                    val nodeId = e.sceneId + "::" + e.label
                    val a = agg.getOrPut(nodeId) { Agg(e.sceneId, e.label, 0, 0) }
                    a.visits++
                    totalChoices++
                    path.add(nodeId)

                    var advanced = false
                    var j = i + 1
                    while (j < events.size) {
                        val n = events[j]
                        if (n is SceneEnter || n is ChoiceMade) {
                            advanced = true
                            break
                        }
                        j++
                    }
                    if (!advanced) {
                        a.drops++
                    }
                }
            }
            if (path.isNotEmpty()) {
                pathCounts[path] = (pathCounts[path] ?: 0) + 1
            }
        }

        val allNodes = agg.map { (nodeId, a) ->
            HeatNode(
                nodeId = nodeId,
                sceneId = a.sceneId,
                label = a.label,
                visits = a.visits,
                drops = a.drops,
                dropRate = a.drops.toDouble() / a.visits,
            )
        }

        val nodes = allNodes.sortedWith(
            compareByDescending<HeatNode> { it.visits }
                .thenByDescending { it.dropRate }
                .thenBy { it.nodeId }
        )

        val churnPoints = allNodes
            .filter { it.dropRate >= dropThreshold && it.visits >= minVisits }
            .sortedWith(
                compareByDescending<HeatNode> { it.dropRate }
                    .thenByDescending { it.visits }
                    .thenBy { it.nodeId }
            )

        val topPaths = pathCounts.entries
            .map { HotPath(it.key, it.value) }
            .sortedWith(
                compareByDescending<HotPath> { it.count }
                    .thenByDescending { it.path.size }
                    .thenBy { it.path.firstOrNull() ?: "" }
            )
            .take(topPathLimit)

        return HeatmapReport(
            sessionCount = sessions.size,
            totalChoices = totalChoices,
            nodes = nodes,
            churnPoints = churnPoints,
            topPaths = topPaths,
        )
    }

    fun analyzeSession(
        events: List<SessionEvent>,
        dropThreshold: Double = 0.5,
        minVisits: Int = 2,
        topPathLimit: Int = 5,
    ): HeatmapReport = analyze(listOf(events), dropThreshold, minVisits, topPathLimit)
}
