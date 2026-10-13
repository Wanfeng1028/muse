
package com.interlude.dsl

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ParserTest {

    private val sample = """
        # 示例剧本
        scene start:
          text: "你站在岔路口，{name}。"
          set courage = 0
          choice "向左走" -> forest
          choice "向右走" -> cave if courage > 0
          jump -> end if courage < 0

        scene forest:
          text: "森林深处传来声响。"
          end
    """.trimIndent()

    @Test
    fun parsesSampleScript() {
        val story = Parser(sample).parse()

        assertEquals(2, story.scenes.size)
        assertEquals("start", story.entry?.id)
        assertEquals("start", story.sceneById("start")?.id)
        assertNull(story.sceneById("missing"))

        val start = story.sceneById("start")!!
        assertEquals(5, start.statements.size)

        val text = start.statements[0] as Text
        assertEquals("你站在岔路口，{name}。", text.value)

        val setVar = start.statements[1] as SetVar
        assertEquals("courage", setVar.name)
        assertEquals(IntLit(0), setVar.expr)

        val choice1 = start.statements[2] as Choice
        assertEquals("向左走", choice1.label)
        assertEquals("forest", choice1.target)
        assertNull(choice1.condition)

        val choice2 = start.statements[3] as Choice
        assertEquals("向右走", choice2.label)
        assertEquals("cave", choice2.target)
        assertEquals(
            Binary(Binary.Op.GT, VarRef("courage"), IntLit(0)),
            choice2.condition
        )

        val forest = story.sceneById("forest")!!
        assertTrue(forest.statements[0] is Text)
        assertTrue(forest.statements[1] is End)

        val jump = start.statements[4] as Jump
        assertEquals("end", jump.target)
        assertEquals(
            Binary(Binary.Op.LT, VarRef("courage"), IntLit(0)),
            jump.condition
        )
    }

    @Test
    fun parsesJumpWithCondition() {
        val src = """
            scene start:
              jump -> end if courage < 0
            scene end:
              end
        """.trimIndent()
        val story = Parser(src).parse()
        val jump = story.sceneById("start")!!.statements[0] as Jump
        assertEquals("end", jump.target)
        assertEquals(
            Binary(Binary.Op.LT, VarRef("courage"), IntLit(0)),
            jump.condition
        )
    }

    @Test
    fun parsesChoiceWithIf() {
        val src = """
            scene start:
              choice "向右走" -> cave if courage > 0
            scene cave:
              end
        """.trimIndent()
        val story = Parser(src).parse()
        val choice = story.sceneById("start")!!.statements[0] as Choice
        assertNotNull(choice.condition)
        assertEquals(
            Binary(Binary.Op.GT, VarRef("courage"), IntLit(0)),
            choice.condition
        )
    }

    @Test
    fun respectsOperatorPrecedence() {
        val src = """
            scene start:
              set x = 1 + 2 * 3
              set y = (1 + 2) * 3
              set z = 1 - 2 - 3
            scene end:
              end
        """.trimIndent()
        val story = Parser(src).parse()
        val stmts = story.sceneById("start")!!.statements

        assertEquals(
            Binary(
                Binary.Op.PLUS,
                IntLit(1),
                Binary(Binary.Op.TIMES, IntLit(2), IntLit(3))
            ),
            (stmts[0] as SetVar).expr
        )
        assertEquals(
            Binary(
                Binary.Op.TIMES,
                Binary(Binary.Op.PLUS, IntLit(1), IntLit(2)),
                IntLit(3)
            ),
            (stmts[1] as SetVar).expr
        )
        assertEquals(
            Binary(
                Binary.Op.MINUS,
                Binary(Binary.Op.MINUS, IntLit(1), IntLit(2)),
                IntLit(3)
            ),
            (stmts[2] as SetVar).expr
        )
    }

    @Test
    fun parsesLogicalAndUnaryOps() {
        val src = """
            scene start:
              set flag = not a and b or c
              set n = -x
            scene end:
              end
        """.trimIndent()
        val story = Parser(src).parse()
        val stmts = story.sceneById("start")!!.statements

        assertEquals(
            Binary(
                Binary.Op.OR,
                Binary(
                    Binary.Op.AND,
                    Not(VarRef("a")),
                    VarRef("b")
                ),
                VarRef("c")
            ),
            (stmts[0] as SetVar).expr
        )
        assertEquals(Neg(VarRef("x")), (stmts[1] as SetVar).expr)
    }

    @Test
    fun extractsPlaceholders() {
        assertEquals(
            listOf("name", "courage"),
            extractPlaceholders("你好 {name}，勇气为 {courage}。")
        )
        assertEquals(
            listOf("name"),
            extractPlaceholders("{name} 和 {name}")
        )
        assertEquals(
            emptyList(),
            extractPlaceholders("没有占位符")
        )
        assertEquals(
            emptyList(),
            extractPlaceholders("非法 {123}")
        )
    }

    @Test
    fun errorOnMissingColonInScene() {
        val src = """
            scene start
              end
        """.trimIndent()
        val err = assertFailsWith<ParseError> { Parser(src).parse() }
        assertEquals(1, err.line)
    }

    @Test
    fun errorOnBadIndent() {
        val src = """
            scene start:
               end
        """.trimIndent()
        val err = assertFailsWith<ParseError> { Parser(src).parse() }
        assertEquals(2, err.line)
    }

    @Test
    fun errorOnUnterminatedString() {
        val src = """
            scene start:
              text: "未闭合
        """.trimIndent()
        val err = assertFailsWith<ParseError> { Parser(src).parse() }
        assertEquals(2, err.line)
    }

    @Test
    fun errorOnInvalidTarget() {
        val src = """
            scene start:
              choice "选项" -> 123bad
        """.trimIndent()
        val err = assertFailsWith<ParseError> { Parser(src).parse() }
        assertEquals(2, err.line)
    }

    @Test
    fun errorOnUnknownStatement() {
        val src = """
            scene start:
              bogus something
        """.trimIndent()
        val err = assertFailsWith<ParseError> { Parser(src).parse() }
        assertEquals(2, err.line)
    }
}
