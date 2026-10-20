package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorDeadEndEmptySceneTest {

    @Test
    fun emptySceneIsDeadEndAtHeaderLine() {
        val source = """
            scene start:
              end
            scene hollow:
            scene tail:
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val deadEnds = issues.filter { it.code == "DEAD_END" }
        assertEquals(1, deadEnds.size, "空场景 hollow 应恰好产生 1 条 DEAD_END，实际为 ${deadEnds.size}")

        val dead = deadEnds.first()
        assertEquals(Severity.WARNING, dead.severity, "DEAD_END 应为 WARNING 级别")
        assertEquals("hollow", dead.sceneId, "DEAD_END 应归属于空场景 hollow")
        assertEquals(3, dead.line, "DEAD_END 行号应为场景头行 3，实际为 ${dead.line}")
        assertTrue(dead.message.contains("hollow"), "DEAD_END 信息应包含场景名 hollow，实际为 ${dead.message}")

        val hollowIssues = issues.filter { it.sceneId == "hollow" }
        assertEquals(2, hollowIssues.size, "hollow 场景应产生 2 条 issue（DEAD_END + UNREACHABLE），实际为 ${hollowIssues.size}")
        assertEquals(setOf("DEAD_END", "UNREACHABLE"), hollowIssues.map { it.code }.toSet(), "hollow 场景的 issue 应为 DEAD_END 与 UNREACHABLE")

        val tailDeadEnds = issues.filter { it.code == "DEAD_END" && it.sceneId == "tail" }
        assertTrue(tailDeadEnds.isEmpty(), "tail 以 end 结尾不应产生 DEAD_END，实际为 ${tailDeadEnds.size}")

        val tailUnreachable = issues.filter { it.code == "UNREACHABLE" && it.sceneId == "tail" }
        assertEquals(1, tailUnreachable.size, "tail 从入口不可达应产生 1 条 UNREACHABLE，实际为 ${tailUnreachable.size}")
        assertEquals(Severity.WARNING, tailUnreachable.first().severity, "UNREACHABLE 应为 WARNING 级别")
        assertEquals(4, tailUnreachable.first().line, "UNREACHABLE 行号应为场景头行 4")
    }

    @Test
    fun endOnlySceneNoDeadEnd() {
        val source = """
            scene start:
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val deadEnds = issues.filter { it.code == "DEAD_END" }
        assertTrue(deadEnds.isEmpty(), "以 end 结尾的场景不应产生 DEAD_END，实际为 ${deadEnds.size}")

        assertTrue(issues.isEmpty(), "仅含 end 的单场景剧本应无任何 issue，实际为 $issues")
    }

    @Test
    fun textOnlySceneDeadEnd() {
        val source = """
            scene start:
              text: "旁白"
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val deadEnds = issues.filter { it.code == "DEAD_END" }
        assertEquals(1, deadEnds.size, "仅有 text 无出口的场景应恰好产生 1 条 DEAD_END，实际为 ${deadEnds.size}")

        val dead = deadEnds.first()
        assertEquals(Severity.WARNING, dead.severity, "DEAD_END 应为 WARNING 级别")
        assertEquals("start", dead.sceneId, "DEAD_END 应归属于场景 start")
        assertEquals(1, dead.line, "DEAD_END 行号应为场景头行 1，实际为 ${dead.line}")
        assertTrue(dead.message.contains("start"), "DEAD_END 信息应包含场景名 start，实际为 ${dead.message}")
        assertFalse(dead.message.isEmpty(), "DEAD_END 信息不应为空")
    }
}