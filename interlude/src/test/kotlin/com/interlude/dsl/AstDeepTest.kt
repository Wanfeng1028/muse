package com.interlude.dsl

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.*

class AstDeepTest {

    // 事实来源：Story.entry 使用 scenes.firstOrNull()，空列表返回 null
    @Test
    fun emptyStoryEntryIsNull() {
        val story = Story(emptyList())
        assertNull(story.entry)
    }

    // 事实来源：Story.sceneById 使用 scenes.firstOrNull { it.id == id }，空列表返回 null
    @Test
    fun emptyStorySceneByIdReturnsNull() {
        val story = Story(emptyList())
        assertNull(story.sceneById("x"))
    }

    // 事实来源：Story.entry 为 scenes.firstOrNull()，返回列表第一个元素而非按 id 排序
    @Test
    fun entryReturnsFirstScene() {
        val s1 = Scene("s1", 1, emptyList())
        val s2 = Scene("s2", 2, emptyList())
        val story = Story(listOf(s2, s1))
        assertEquals(s2, story.entry)
        assertNotEquals(s1, story.entry)
    }

    // 事实来源：Story.sceneById 使用 firstOrNull { it.id == id }，可命中中间位置
    @Test
    fun sceneByIdFindsMiddleScene() {
        val s1 = Scene("a", 1, emptyList())
        val s2 = Scene("b", 2, emptyList())
        val s3 = Scene("c", 3, emptyList())
        val story = Story(listOf(s1, s2, s3))
        assertEquals(s2, story.sceneById("b"))
    }

    // 事实来源：Story.sceneById 的 id 比较为字符串相等，大小写敏感
    @Test
    fun sceneByIdIsCaseSensitive() {
        val scene = Scene("S1", 1, emptyList())
        val story = Story(listOf(scene))
        assertEquals(scene, story.sceneById("S1"))
        assertNull(story.sceneById("s1"))
    }

    // 事实来源：Text/Choice/Jump/End/SetVar 均实现 Statement 接口且携带 line
    @Test
    fun allStatementImplementationsCarryLine() {
        val text: Statement = Text(10, "hello")
        val setVar: Statement = SetVar(20, "x", IntLit(1))
        val choice: Statement = Choice(30, "go", "s2", null)
        val jump: Statement = Jump(40, "s3", null)
        val end: Statement = End(50)

        assertTrue(text is Statement)
        assertTrue(setVar is Statement)
        assertTrue(choice is Statement)
        assertTrue(jump is Statement)
        assertTrue(end is Statement)

        assertEquals(10, text.line)
        assertEquals(20, setVar.line)
        assertEquals(30, choice.line)
        assertEquals(40, jump.line)
        assertEquals(50, end.line)
    }

    // 事实来源：Text 为 data class，相等性基于全部构造参数，copy 可修改 value
    @Test
    fun textDataClassEqualityAndCopy() {
        val a = Text(1, "a")
        val b = Text(1, "a")
        assertEquals(a, b)
        assertNotEquals(a, a.copy(value = "b"))
    }

    // 事实来源：Choice.condition 类型为 Expr?，允许 null 与表达式
    @Test
    fun choiceConditionNullableOrExpr() {
        val noCondition = Choice(1, "go", "s2", null)
        assertNull(noCondition.condition)

        val withCondition = Choice(2, "go", "s2", VarRef("hp"))
        assertEquals(VarRef("hp"), withCondition.condition)
    }

    // 事实来源：Binary.Op 枚举定义包含 12 个常量，含 GT
    @Test
    fun binaryOpHasTwelveValuesIncludingGt() {
        val values = Binary.Op.values()
        assertEquals(12, values.size)
        assertTrue(values.contains(Binary.Op.GT))
        assertEquals(
            listOf(
                Binary.Op.PLUS, Binary.Op.MINUS, Binary.Op.TIMES, Binary.Op.DIV,
                Binary.Op.GT, Binary.Op.LT, Binary.Op.GTE, Binary.Op.LTE,
                Binary.Op.EQ, Binary.Op.NEQ, Binary.Op.AND, Binary.Op.OR
            ),
            values.toList()
        )
    }

    // 事实来源：Binary 持有 op/left/right，Not 持有 operand，可逐层断言嵌套结构
    @Test
    fun nestedExpressionStructure() {
        val expr = Binary(
            Binary.Op.AND,
            Binary(Binary.Op.GT, VarRef("hp"), IntLit(0)),
            Not(VarRef("dead"))
        )
        assertEquals(Binary.Op.AND, expr.op)
        val left = expr.left as Binary
        assertEquals(Binary.Op.GT, left.op)
        assertEquals(VarRef("hp"), left.left)
        assertEquals(IntLit(0), left.right)
        val right = expr.right as Not
        assertEquals(VarRef("dead"), right.operand)
    }

    // 事实来源：Neg 为 data class 持有 operand，可包裹 IntLit
    @Test
    fun negWrapsOperand() {
        val neg = Neg(IntLit(5))
        assertEquals(IntLit(5), neg.operand)
        assertEquals(Neg(IntLit(5)), neg)
    }

    // 事实来源：Scene.statements 为 List，保持插入顺序
    @Test
    fun sceneStatementsPreserveInsertionOrder() {
        val t1 = Text(1, "one")
        val t2 = Text(2, "two")
        val t3 = Text(3, "three")
        val scene = Scene("s", 1, listOf(t1, t2, t3))
        assertEquals(listOf<Statement>(t1, t2, t3), scene.statements)
        assertEquals(t1, scene.statements[0])
        assertEquals(t2, scene.statements[1])
        assertEquals(t3, scene.statements[2])
    }

    // 事实来源：Story 为 data class，copy 替换 scenes 后 entry 基于新列表重新计算
    @Test
    fun storyCopyReplacesScenesAndEntry() {
        val s1 = Scene("s1", 1, emptyList())
        val s2 = Scene("s2", 2, emptyList())
        val story = Story(listOf(s1))
        assertEquals(s1, story.entry)
        val copied = story.copy(scenes = listOf(s2))
        assertEquals(s2, copied.entry)
        assertNotEquals(s1, copied.entry)
    }
}
