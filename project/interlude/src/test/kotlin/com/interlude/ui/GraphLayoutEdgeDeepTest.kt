package com.interlude.ui

import com.interlude.dsl.Choice
import com.interlude.dsl.Jump
import com.interlude.dsl.Scene
import com.interlude.dsl.Statement
import com.interlude.dsl.Story
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class GraphLayoutEdgeDeepTest {

    private fun scene(id: String, vararg statements: Statement) = Scene(id, 0, statements.toList())

    // 空 story：layout 中 entry 为 null 时直接 return positions to edges，故两者皆空
    @Test
    fun emptyStoryYieldsEmptyPositionsAndEdges() {
        val (positions, edges) = GraphLayout.layout(Story(emptyList()))
        assertTrue(positions.isEmpty())
        assertTrue(edges.isEmpty())
    }

    // 菱形 a->b,a->c,b->d,c->d：BFS 使 b、c 同层(x=260f)，d 层为 2(x=520f)，b/c 同层按 idx 排 y 不同
    @Test
    fun diamondConvergencePlacesMergeAtLevelTwo() {
        val story = Story(
            listOf(
                scene("a", Choice(0, "toB", "b", null), Choice(0, "toC", "c", null)),
                scene("b", Jump(0, "d", null)),
                scene("c", Jump(0, "d", null)),
                scene("d")
            )
        )
        val (positions, _) = GraphLayout.layout(story)
        assertEquals(520f, positions.getValue("d").x)
        assertEquals(260f, positions.getValue("b").x)
        assertEquals(260f, positions.getValue("c").x)
        assertTrue(positions.getValue("b").y != positions.getValue("c").y)
    }

    // 长链 a->b->c->d：BFS 逐层 +1，x 依次为 0、260、520、780
    @Test
    fun longChainIncrementsXBy260PerLevel() {
        val story = Story(
            listOf(
                scene("a", Jump(0, "b", null)),
                scene("b", Jump(0, "c", null)),
                scene("c", Jump(0, "d", null)),
                scene("d")
            )
        )
        val (positions, _) = GraphLayout.layout(story)
        assertEquals(0f, positions.getValue("a").x)
        assertEquals(260f, positions.getValue("b").x)
        assertEquals(520f, positions.getValue("c").x)
        assertEquals(780f, positions.getValue("d").x)
    }

    // 不可达 scene：maxLevel=1(a->b)，孤立 z 走 extraLevel = maxLevel+1 = 2，故 z.x == 520f
    @Test
    fun unreachableSceneGetsExtraLevelAfterMaxLevel() {
        val story = Story(
            listOf(
                scene("a", Jump(0, "b", null)),
                scene("b"),
                scene("z")
            )
        )
        val (positions, _) = GraphLayout.layout(story)
        assertEquals(260f, positions.getValue("b").x)
        assertEquals(520f, positions.getValue("z").x)
    }

    // 未定义 target：a->ghost 且 ghost 无 scene，undefined 处理使其层为 levelOf[a]+1，故 ghost.x == a.x+260f
    @Test
    fun undefinedTargetPlacedOneLevelRightOfSource() {
        val story = Story(listOf(scene("a", Jump(0, "ghost", null))))
        val (positions, edges) = GraphLayout.layout(story)
        assertTrue(positions.containsKey("ghost"))
        assertEquals(positions.getValue("a").x + 260f, positions.getValue("ghost").x)
        assertEquals(Edge("a", "ghost", null), edges.single())
    }

    // Edge 构造：Choice 传 st.label，Jump 传 null，故 Choice 边 label 有值、Jump 边 label 为 null
    @Test
    fun choiceEdgeCarriesLabelWhileJumpEdgeHasNullLabel() {
        val story = Story(
            listOf(
                scene("a", Choice(0, "go", "b", null)),
                scene("b", Jump(0, "c", null)),
                scene("c")
            )
        )
        val (_, edges) = GraphLayout.layout(story)
        val choiceEdge = edges.first { it.from == "a" }
        val jumpEdge = edges.first { it.from == "b" }
        assertEquals(Edge("a", "b", "go"), choiceEdge)
        assertNotNull(choiceEdge.label)
        assertNull(jumpEdge.label)
        assertEquals(Edge("b", "c", null), jumpEdge)
    }

    // 同层排序：byLevel 内 ids.sorted()，先写 c 后写 b 也仍 b 在前，故 b.y < c.y
    @Test
    fun sameLevelNodesSortedAlphabeticallyById() {
        val story = Story(
            listOf(
                scene("a", Choice(0, "toC", "c", null), Choice(0, "toB", "b", null)),
                scene("b"),
                scene("c")
            )
        )
        val (positions, _) = GraphLayout.layout(story)
        assertEquals(260f, positions.getValue("b").x)
        assertEquals(260f, positions.getValue("c").x)
        assertTrue(positions.getValue("b").y < positions.getValue("c").y)
    }

    // 自环 a->a：target 已在 levelOf 中不再入队，a 层保持 0，positions 含 a 且 x == 0f
    @Test
    fun selfLoopKeepsNodeAtLevelZero() {
        val story = Story(listOf(scene("a", Jump(0, "a", null))))
        val (positions, edges) = GraphLayout.layout(story)
        assertTrue(positions.containsKey("a"))
        assertEquals(0f, positions.getValue("a").x)
        assertEquals(Edge("a", "a", null), edges.single())
    }
}
