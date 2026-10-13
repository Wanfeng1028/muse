
package com.interlude.ui

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class GraphLayoutTest {

    @Test
    fun twoNodeStoryLevelsIncrease() {
        val src = """
            scene a:
              text: "a"
              jump -> b
            scene b:
              text: "b"
              end
        """.trimIndent()
        val story = Parser(src).parse()
        val (pos, edges) = GraphLayout.layout(story)
        val a = pos.getValue("a")
        val b = pos.getValue("b")
        assertTrue(b.x > a.x, "b 应在 a 右侧")
        assertEquals(260f, b.x - a.x)
        assertEquals(1, edges.size)
        assertEquals("a", edges[0].from)
        assertEquals("b", edges[0].to)
    }

    @Test
    fun forkSameLevelDifferentY() {
        val src = """
            scene start:
              text: "s"
              choice "left" -> l
              choice "right" -> r
            scene l:
              text: "l"
              end
            scene r:
              text: "r"
              end
        """.trimIndent()
        val story = Parser(src).parse()
        val (pos, _) = GraphLayout.layout(story)
        val l = pos.getValue("l")
        val r = pos.getValue("r")
        assertEquals(l.x, r.x)
        assertTrue(l.y != r.y, "同层节点 y 应不同")
    }

    @Test
    fun edgesCarryFromTo() {
        val src = """
            scene a:
              text: "a"
              choice "go" -> b
            scene b:
              text: "b"
              end
        """.trimIndent()
        val story = Parser(src).parse()
        val (_, edges) = GraphLayout.layout(story)
        assertEquals(1, edges.size)
        assertEquals("a", edges[0].from)
        assertEquals("b", edges[0].to)
        assertEquals("go", edges[0].label)
    }
}
