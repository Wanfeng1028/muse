package com.interlude.replay

data class PathStat(val path: List<String>, val count: Int, val share: Double)

data class ChoiceDist(
    val sceneId: String,
    val label: String,
    val target: String,
    val picks: Int,
    val share: Double
)

data class ChurnSpot(val sceneId: String, val sessions: Int, val rate: Double)

data class AggregateReport(
    val sessionCount: Int,
    val totalEvents: Int,
    val topPaths: List<PathStat>,
    val choiceDists: List<ChoiceDist>,
    val churnSpots: List<ChurnSpot>
)

object AggregateAnalyzer {
    fun analyze(sessions: List<List<SessionEvent>>, topN: Int = 10): AggregateReport {
        val sessionCount = sessions.size
        if (sessionCount == 0) {
            return AggregateReport(
                sessionCount = 0,
                totalEvents = 0,
                topPaths = emptyList(),
                choiceDists = emptyList(),
                churnSpots = emptyList()
            )
        }

        val totalEvents = sessions.sumOf { it.size }

        // ---- 常用路径 ----
        val pathCounts = LinkedHashMap<List<String>, Int>()
        for (session in sessions) {
            val path = extractPath(session)
            if (path.isEmpty()) continue
            pathCounts[path] = (pathCounts[path] ?: 0) + 1
        }
        val topPaths = pathCounts.entries
            .map { PathStat(it.key, it.value, it.value.toDouble() / sessionCount) }
            .sortedWith(compareByDescending<PathStat> { it.count }.thenBy { pathSortKey(it.path) })
            .take(topN)

        // ---- 抉择点分布 ----
        // sceneId -> (label -> (target, picks))
        val choiceByScene = LinkedHashMap<String, LinkedHashMap<String, Pair<String, Int>>>()
        for (session in sessions) {
            for (event in session) {
                if (event is ChoiceMade) {
                    val inner = choiceByScene.getOrPut(event.sceneId) { LinkedHashMap() }
                    val prev = inner[event.label]
                    if (prev == null) {
                        inner[event.label] = event.target to 1
                    } else {
                        inner[event.label] = prev.first to (prev.second + 1)
                    }
                }
            }
        }
        val choiceDists = mutableListOf<ChoiceDist>()
        for (sceneId in choiceByScene.keys.sorted()) {
            val inner = choiceByScene.getValue(sceneId)
            val total = inner.values.sumOf { it.second }
            val sorted = inner.entries
                .map { Triple(it.key, it.value.first, it.value.second) }
                .sortedWith(compareByDescending<Triple<String, String, Int>> { it.third }.thenBy { it.first })
            for (entry in sorted) {
                val share = if (total == 0) 0.0 else entry.third.toDouble() / total
                choiceDists.add(ChoiceDist(sceneId, entry.first, entry.second, entry.third, share))
            }
        }

        // ---- 流失点 ----
        val churnCounts = LinkedHashMap<String, Int>()
        for (session in sessions) {
            val hasEnd = session.any { it is SessionEnd }
            if (hasEnd) continue
            val lastSceneId = lastSceneIdOrNull(session)
            if (lastSceneId == null) continue
            churnCounts[lastSceneId] = (churnCounts[lastSceneId] ?: 0) + 1
        }
        val churnSpots = churnCounts.entries
            .map { ChurnSpot(it.key, it.value, it.value.toDouble() / sessionCount) }
            .sortedWith(compareByDescending<ChurnSpot> { it.sessions }.thenBy { it.sceneId })

        return AggregateReport(
            sessionCount = sessionCount,
            totalEvents = totalEvents,
            topPaths = topPaths,
            choiceDists = choiceDists,
            churnSpots = churnSpots
        )
    }

    private fun extractPath(session: List<SessionEvent>): List<String> {
        val path = mutableListOf<String>()
        for (event in session) {
            if (event is SceneEnter) {
                if (path.isEmpty() || path.last() != event.sceneId) {
                    path.add(event.sceneId)
                }
            }
        }
        return path
    }

    private fun lastSceneIdOrNull(session: List<SessionEvent>): String? {
        var last: String? = null
        for (event in session) {
            when (event) {
                is SceneEnter -> last = event.sceneId
                is ChoiceMade -> last = event.sceneId
                else -> {}
            }
        }
        return last
    }

    private fun pathSortKey(path: List<String>): String = path.joinToString("\u0000")
}
