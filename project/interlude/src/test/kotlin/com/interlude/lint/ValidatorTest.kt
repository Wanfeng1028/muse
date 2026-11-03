
package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ValidatorTest {

    @Test
    fun `undefined target reported with correct line`() {
        val src = """
            scene start:
              text: "hello"
              choice "go" -> missing
        """.trimIndent()
        val story = Parser(src).parse()
        val issues = Validator.validate(story)
        val issue = issues.firstOrNull { it.code == "UNDEFINED_TARGET" }
        assertTrue(issue != null, "应当报告 UNDEFINED_TARGET")
        assertEquals(Severity.ERROR, issue!!.severity)
        assertEquals("start", issue.sceneId)
        assertEquals(3, issue.line)
    }

    @Test
    fun `dead end scene reported`() {
        val src = """
            scene start:
              text: "hello"
        """.trimIndent()
        val story = Parser(src).parse()
        val issues = Validator.validate(story)
        assertTrue(issues.any { it.code == "DEAD_END" && it.sceneId == "start" })
    }

    @Test
    fun `unreachable scene reported`() {
        val src = """
            scene start:
              text: "hi"
              jump -> finish
            scene finish:
              text: "done"
              end
            scene orphan:
              text: "orphan"
              end
        """.trimIndent()
        val story = Parser(src).parse()
        val issues = Validator.validate(story)
        assertTrue(issues.any { it.code == "UNREACHABLE" && it.sceneId == "orphan" })
        assertTrue(issues.none { it.code == "UNREACHABLE" && it.sceneId == "finish" })
    }

    @Test
    fun `uninitialized var reported`() {
        val src = """
            scene start:
              text: "value is {foo}"
              end
        """.trimIndent()
        val story = Parser(src).parse()
        val issues = Validator.validate(story)
        assertTrue(issues.any { it.code == "UNINIT_VAR" && it.line == 2 })
    }

    @Test
    fun `always false condition reported`() {
        val src = """
            scene start:
              jump -> end_scene if 1 > 2
            scene end_scene:
              text: "done"
              end
        """.trimIndent()
        val story = Parser(src).parse()
        val issues = Validator.validate(story)
        assertTrue(issues.any { it.code == "ALWAYS_FALSE" })
    }

    @Test
    fun `clean story returns no issues`() {
        val src = """
            scene start:
              set x = 1
              text: "hi {x}"
              choice "go" -> finish
            scene finish:
              text: "done"
              end
        """.trimIndent()
        val story = Parser(src).parse()
        val issues = Validator.validate(story)
        assertEquals(emptyList(), issues)
    }
}
