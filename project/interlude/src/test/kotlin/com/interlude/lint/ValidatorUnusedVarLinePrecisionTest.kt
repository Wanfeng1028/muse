package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ValidatorUnusedVarLinePrecisionTest {

    @Test
    fun linePointsToUnusedSetNotUsedOnes() {
        val source = """
scene start:
  set a = 1
  set bbb = 2
  set ccc = 3
  text: "{a}"
  end
""".trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(2, unused.size, "应恰好报告两条 UNUSED_VAR")

        val sorted = unused.sortedBy { it.line }
        assertEquals(3, sorted[0].line, "第一条 UNUSED_VAR 行号应为首次 set bbb 的第 3 行")
        assertEquals(4, sorted[1].line, "第二条 UNUSED_VAR 行号应为首次 set ccc 的第 4 行")

        assertEquals(Severity.WARNING, sorted[0].severity, "UNUSED_VAR 严重级别应为 WARNING")
        assertEquals(Severity.WARNING, sorted[1].severity, "UNUSED_VAR 严重级别应为 WARNING")

        assertTrue(sorted[0].message.contains("bbb"), "第一条消息应包含变量名 bbb")
        assertTrue(sorted[1].message.contains("ccc"), "第二条消息应包含变量名 ccc")
    }

    @Test
    fun sceneIdIsWhereSetLives() {
        val source = """
scene start:
  set ok = 1
  text: "{ok}"
  jump -> b

scene b:
  set ghost = 9
  end
""".trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unused.size, "应恰好报告一条 UNUSED_VAR")

        val issue = unused[0]
        assertEquals("b", issue.sceneId, "UNUSED_VAR 的 sceneId 应为 set 所在场景 b")
        assertEquals(7, issue.line, "UNUSED_VAR 行号应为 set ghost 所在第 7 行")
        assertEquals(Severity.WARNING, issue.severity, "UNUSED_VAR 严重级别应为 WARNING")
        assertTrue(issue.message.contains("ghost"), "消息应包含变量名 ghost")
    }

    @Test
    fun firstSetLineReportedForRepeatedSets() {
        val source = """
scene start:
  set dup = 1
  set dup = 2
  end
""".trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unused.size, "同一变量多处 set 应只报告一条 UNUSED_VAR")

        val issue = unused[0]
        assertEquals(2, issue.line, "应报告首次 set dup 的行号 2，而非第二次的 3")
        assertEquals("start", issue.sceneId, "sceneId 应为 set 所在场景 start")
        assertEquals(Severity.WARNING, issue.severity, "UNUSED_VAR 严重级别应为 WARNING")
        assertTrue(issue.message.contains("dup"), "消息应包含变量名 dup")
    }
}