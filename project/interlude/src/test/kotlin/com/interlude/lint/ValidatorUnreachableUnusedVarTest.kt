package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorUnreachableUnusedVarTest {

    private fun parse(source: String) = Parser(source).parse()

    @Test
    fun unusedSetInUnreachableSceneWarns() {
        val source = buildString {
            appendLine("scene start:")
            appendLine("  text: \"开始\"")
            appendLine("  end")
            appendLine("scene dead:")
            appendLine("  set ghost = 1")
            appendLine("  end")
        }
        val issues = Validator.validate(parse(source))

        val unreachable = issues.filter { it.code == "UNREACHABLE" }
        assertEquals(1, unreachable.size, "应恰好报告 1 条 UNREACHABLE")
        assertEquals("dead", unreachable[0].sceneId, "UNREACHABLE 应指向场景 dead")
        assertEquals(4, unreachable[0].line, "UNREACHABLE 行号应为 dead 场景声明行 4")
        assertEquals(Severity.WARNING, unreachable[0].severity, "UNREACHABLE 应为 WARNING")

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unused.size, "应恰好报告 1 条 UNUSED_VAR")
        assertEquals("dead", unused[0].sceneId, "UNUSED_VAR 应指向不可达场景 dead")
        assertEquals(5, unused[0].line, "UNUSED_VAR 行号应为 set ghost 所在行 5")
        assertEquals(Severity.WARNING, unused[0].severity, "UNUSED_VAR 应为 WARNING")
        assertTrue(unused[0].message.contains("ghost"), "UNUSED_VAR 消息应包含变量名 ghost")
    }

    @Test
    fun usedOnlyInUnreachableSceneNoUnusedWarn() {
        val source = buildString {
            appendLine("scene start:")
            appendLine("  set hp = 100")
            appendLine("  text: \"开始\"")
            appendLine("  end")
            appendLine("scene dead:")
            appendLine("  text: \"血量 {hp}\"")
            appendLine("  end")
        }
        val issues = Validator.validate(parse(source))

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertTrue(unused.isEmpty(), "hp 在不可达场景文本中被引用，不应报告 UNUSED_VAR")

        val unreachable = issues.filter { it.code == "UNREACHABLE" }
        assertEquals(1, unreachable.size, "应恰好报告 1 条 UNREACHABLE")
        assertEquals("dead", unreachable[0].sceneId, "UNREACHABLE 应指向场景 dead")
        assertEquals(5, unreachable[0].line, "UNREACHABLE 行号应为 dead 场景声明行 5")
    }

    @Test
    fun unreachableSceneChainUnusedPropagates() {
        val source = buildString {
            appendLine("scene start:")
            appendLine("  end")
            appendLine("scene d1:")
            appendLine("  set v1 = 1")
            appendLine("  jump -> d2")
            appendLine("scene d2:")
            appendLine("  set v2 = v1")
            appendLine("  end")
        }
        val issues = Validator.validate(parse(source))

        val unreachable = issues.filter { it.code == "UNREACHABLE" }
        assertEquals(2, unreachable.size, "应恰好报告 2 条 UNREACHABLE")
        val unreachableIds = unreachable.map { it.sceneId }.toSet()
        assertTrue(unreachableIds.contains("d1"), "UNREACHABLE 应包含 d1")
        assertTrue(unreachableIds.contains("d2"), "UNREACHABLE 应包含 d2")

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unused.size, "应恰好报告 1 条 UNUSED_VAR")
        assertTrue(unused[0].message.contains("v2"), "UNUSED_VAR 消息应包含变量名 v2")
        assertEquals("d2", unused[0].sceneId, "UNUSED_VAR 应指向 d2 中的 set v2")

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertTrue(uninit.isEmpty(), "v1 已被 set，v2 右值引用 v1 不应报 UNINIT_VAR")
    }
}