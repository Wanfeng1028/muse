package com.interlude.dsl

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertNotNull

class ParserDeepTest {

    private fun story(src: String): Story = Parser(src).parse()

    private fun fail(src: String): ParseError = assertFailsWith<ParseError> { Parser(src).parse() }

    private fun firstSet(src: String): SetVar {
        val s = story(src)
        val stmt = s.entry!!.statements.first()
        return stmt as SetVar
    }

    // 1
    @Test
    fun deeplyNestedParens() {
        val set = firstSet(
            """
            scene a:
              set x = (((((1 + 2)))))
              end
            """.trimIndent()
        )
        val e = set.expr
        assertTrue(e is Binary)
        assertEquals(Binary.Op.PLUS, e.op)
        assertEquals(IntLit(1L), e.left)
        assertEquals(IntLit(2L), e.right)
    }

    // 1b
    @Test
    fun mixedParens() {
        val set = firstSet(
            """
            scene a:
              set x = (1 + 2) * (3 - 4)
              end
            """.trimIndent()
        )
        val e = set.expr as Binary
        assertEquals(Binary.Op.TIMES, e.op)
        val l = e.left as Binary
        assertEquals(Binary.Op.PLUS, l.op)
        assertEquals(IntLit(1L), l.left)
        assertEquals(IntLit(2L), l.right)
        val r = e.right as Binary
        assertEquals(Binary.Op.MINUS, r.op)
        assertEquals(IntLit(3L), r.left)
        assertEquals(IntLit(4L), r.right)
    }

    // 2
    @Test
    fun illegalTokenReportsLine() {
        val err = fail(
            """
            scene a:
              set x = 1 @ 2
              end
            """.trimIndent()
        )
        assertEquals(2, err.line)
    }

    // 3
    @Test
    fun choiceMissingArrow() {
        val err = fail(
            """
            scene a:
              choice "去" forest
              end
            """.trimIndent()
        )
        assertEquals(2, err.line)
    }

    // 4
    @Test
    fun jumpMissingTarget() {
        val err = fail(
            """
            scene a:
              jump ->
              end
            """.trimIndent()
        )
        assertEquals(2, err.line)
    }

    // 5
    @Test
    fun textExtraContent() {
        val err = fail(
            """
            scene a:
              text: "hi" extra
              end
            """.trimIndent()
        )
        assertEquals(2, err.line)
    }

    // 6
    @Test
    fun hugeFile() {
        val sb = StringBuilder()
        for (i in 0 until 1500) {
            sb.append("scene s").append(i).append(":\n")
            sb.append("  text: \"line").append(i).append("\"\n")
            sb.append("  end\n")
        }
        val s = Parser(sb.toString()).parse()
        assertEquals(1500, s.scenes.size)
        assertEquals("s0", s.entry!!.id)
    }

    // 7
    @Test
    fun commentsAndLineNumbers() {
        val src = "# comment\n\nscene a:\n  bogus statement\n  end"
        val err = fail(src)
        assertEquals(4, err.line)
    }

    // 8
    @Test
    fun crlfLineEndings() {
        val src = "scene start:\r\n  text: \"a\"\r\n  end"
        val s = Parser(src).parse()
        assertEquals(1, s.scenes.size)
        assertEquals("start", s.entry!!.id)
        val t = s.entry!!.statements[0] as Text
        assertEquals("a", t.value)
    }

    // 9
    @Test
    fun invalidSceneIdNumeric() {
        val err = fail("scene 123abc:\n  end")
        assertEquals(1, err.line)
    }

    // 9b
    @Test
    fun invalidSceneIdEmpty() {
        val err = fail("scene ::")
        assertEquals(1, err.line)
    }

    // 10
    @Test
    fun indentOneSpace() {
        val err = fail("scene a:\n text: \"x\"\n end")
        assertTrue(err.message!!.contains("缩进必须为 2 个空格"))
    }

    // 10b
    @Test
    fun indentThreeSpaces() {
        val err = fail("scene a:\n   text: \"x\"\n   end")
        assertTrue(err.message!!.contains("缩进必须为 2 个空格"))
    }

    // 11
    @Test
    fun topLevelIndentedStatement() {
        val err = fail("scene a:\n    text: \"x\"")
        assertTrue(err.message!!.contains("缩进必须为 2 个空格"))
    }

    // 12
    @Test
    fun escapesInText() {
        val s = story("scene a:\n  text: \"a\\\"b\\\\c\\nd\\te\\qf\"\n  end")
        val t = s.entry!!.statements[0] as Text
        assertEquals("a\"b\\c\nd\teqf", t.value)
    }

    // 13
    @Test
    fun trailingBackslashUnclosed() {
        val err = fail("scene a:\n  text: \"abc\\\n  end")
        assertEquals(2, err.line)
    }

    // 14
    @Test
    fun ifMissingCondition() {
        val err = fail("scene a:\n  jump -> b if\n  end")
        assertTrue(err.message!!.contains("if 缺少条件表达式"))
    }

    // 15
    @Test
    fun ifxMisjudged() {
        val err = fail("scene a:\n  choice \"x\" -> b ifx\n  end")
        assertEquals(2, err.line)
    }

    // 16
    @Test
    fun setInvalidVarName() {
        val err = fail("scene a:\n  set 1x = 2\n  end")
        assertEquals(2, err.line)
    }

    // 16b
    @Test
    fun setMissingEquals() {
        val err = fail("scene a:\n  set x 2\n  end")
        assertEquals(2, err.line)
    }

    // 17
    @Test
    fun keywordBoundary() {
        val s = story(
            """
            scene a:
              set ordinary = 1
              set x = ordinary or 1
              end
            """.trimIndent()
        )
        val set = s.entry!!.statements[1] as SetVar
        val e = set.expr as Binary
        assertEquals(Binary.Op.OR, e.op)
        assertEquals(VarRef("ordinary"), e.left)
        assertEquals(IntLit(1L), e.right)
    }

    // 18
    @Test
    fun booleanAndNegLiterals() {
        val s = story(
            """
            scene a:
              set a = true
              set b = not false
              set c = -5
              end
            """.trimIndent()
        )
        val stmts = s.entry!!.statements
        assertEquals(IntLit(1L), (stmts[0] as SetVar).expr)
        assertEquals(Not(IntLit(0L)), (stmts[1] as SetVar).expr)
        assertEquals(Neg(IntLit(5L)), (stmts[2] as SetVar).expr)
    }

    // 19
    @Test
    fun emptyInput() {
        val err = fail("")
        assertEquals(1, err.line)
    }

    // 19b
    @Test
    fun onlyComments() {
        val err = fail("# xxx\n# yyy")
        assertEquals(1, err.line)
    }

    // 20
    @Test
    fun duplicateSceneId() {
        val s = story(
            """
            scene a:
              text: "first"
              end
            scene a:
              text: "second"
              end
            """.trimIndent()
        )
        assertEquals(2, s.scenes.size)
        val found = s.sceneById("a")
        assertNotNull(found)
        val t = found.statements[0] as Text
        assertEquals("first", t.value)
    }

    // 21
    @Test
    fun placeholdersDedup() {
        assertEquals(listOf("a", "b"), extractPlaceholders("{a} 和 {b} 再 {a}"))
    }

    // 21b
    @Test
    fun placeholdersEscaped() {
        assertEquals(listOf("b"), extractPlaceholders("\\{a} 真 {b}"))
    }

    // 21c
    @Test
    fun placeholdersInvalidId() {
        assertEquals(listOf("ok"), extractPlaceholders("{1x} {ok}"))
    }

    // 21d
    @Test
    fun placeholdersUnclosed() {
        assertEquals(emptyList<String>(), extractPlaceholders("{"))
    }

    // 21e
    @Test
    fun placeholdersEmpty() {
        assertEquals(emptyList<String>(), extractPlaceholders("{}"))
    }

    // 22
    @Test
    fun operatorMatrix() {
        assertEquals(Binary.Op.NEQ, (firstSet("scene a:\n  set x = 1 != 2\n  end").expr as Binary).op)
        assertEquals(Binary.Op.LTE, (firstSet("scene a:\n  set x = 3 <= 4\n  end").expr as Binary).op)
        assertEquals(Binary.Op.GTE, (firstSet("scene a:\n  set x = 5 >= 6\n  end").expr as Binary).op)
        assertEquals(Binary.Op.DIV, (firstSet("scene a:\n  set x = 7 / 2\n  end").expr as Binary).op)
    }

    // extra: choice with condition parses
    @Test
    fun choiceWithCondition() {
        val s = story(
            """
            scene a:
              choice "go" -> b if x > 1
              end
            """.trimIndent()
        )
        val c = s.entry!!.statements[0] as Choice
        assertEquals("go", c.label)
        assertEquals("b", c.target)
        val cond = c.condition as Binary
        assertEquals(Binary.Op.GT, cond.op)
    }

    // extra: jump without condition -> null
    @Test
    fun jumpNoCondition() {
        val s = story(
            """
            scene a:
              jump -> b
              end
            """.trimIndent()
        )
        val j = s.entry!!.statements[0] as Jump
        assertEquals("b", j.target)
        assertNull(j.condition)
    }

    // extra: end statement
    @Test
    fun endStatement() {
        val s = story(
            """
            scene a:
              end
            """.trimIndent()
        )
        assertTrue(s.entry!!.statements[0] is End)
    }

    // extra: text without colon error
    @Test
    fun textMissingColon() {
        val err = fail("scene a:\n  text \"x\"\n  end")
        assertEquals(2, err.line)
    }

    // extra: empty expression after equals
    @Test
    fun setMissingExpression() {
        val err = fail("scene a:\n  set x =\n  end")
        assertEquals(2, err.line)
    }

    // extra: missing right paren
    @Test
    fun missingRightParen() {
        val err = fail("scene a:\n  set x = (1 + 2\n  end")
        assertEquals(2, err.line)
    }

    // extra: empty expression
    @Test
    fun emptyExpression() {
        val err = fail("scene a:\n  set x = \n  end")
        assertEquals(2, err.line)
    }
}
