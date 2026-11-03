
package com.interlude.ui

import com.interlude.dsl.Story
import com.interlude.dsl.Statement
import com.interlude.dsl.Choice
import com.interlude.dsl.Jump

data class NodePos(val x: Float, val y: Float)
data class Edge(val from: String, val to: String, val label: String?)

object GraphLayout {
    fun layout(story: Story): Pair<Map<String, NodePos>, List<Edge>> {
        val scenes = story.scenes
        val byId = scenes.associateBy { it.id }
        val edges = mutableListOf<Edge>()

        val outgoing: MutableMap<String, MutableList<Pair<String, String?>>> = mutableMapOf()
        for (s in scenes) {
            val list = outgoing.getOrPut(s.id) { mutableListOf() }
            for (st in s.statements) {
                when (st) {
                    is Choice -> {
                        edges.add(Edge(s.id, st.target, st.label))
                        list.add(st.target to st.label)
                    }
                    is Jump -> {
                        edges.add(Edge(s.id, st.target, null))
                        list.add(st.target to null)
                    }
                    else -> {}
                }
            }
        }

        val positions = mutableMapOf<String, NodePos>()
        val entry = scenes.firstOrNull()?.id ?: return positions to edges

        val levelOf = mutableMapOf<String, Int>()
        val queue = ArrayDeque<String>()
        levelOf[entry] = 0
        queue.add(entry)
        while (queue.isNotEmpty()) {
            val cur = queue.removeFirst()
            val lvl = levelOf.getValue(cur)
            val nexts = outgoing[cur] ?: emptyList()
            for ((target, _) in nexts) {
                if (target !in levelOf) {
                    levelOf[target] = lvl + 1
                    queue.add(target)
                }
            }
        }

        // 未可达但有定义的场景：放到最后层
        val maxLevel = levelOf.values.maxOrNull() ?: 0
        var extraLevel = maxLevel + 1
        for (s in scenes) {
            if (s.id !in levelOf) {
                levelOf[s.id] = extraLevel
                extraLevel++
            }
        }

        // 未定义的 target：放在源节点右侧一层
        val allTargets = edges.map { it.to }.toSet()
        val undefined = allTargets.filter { it !in byId }
        for (u in undefined) {
            if (u !in levelOf) {
                // 找指向它的最小层
                val srcLevel = edges.filter { it.to == u }.mapNotNull { levelOf[it.from] }.minOrNull() ?: 0
                levelOf[u] = srcLevel + 1
            }
        }

        val byLevel: Map<Int, List<String>> = levelOf.entries
            .groupBy({ it.value }, { it.key })
            .mapValues { (_, v) -> v.sorted() }

        for ((lvl, ids) in byLevel) {
            ids.forEachIndexed { idx, id ->
                positions[id] = NodePos(lvl * 260f, idx * 130f + 40f)
            }
        }

        return positions to edges
    }
}
