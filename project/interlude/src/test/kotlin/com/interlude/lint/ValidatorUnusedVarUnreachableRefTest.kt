package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorUnusedVarUnreachableRefTest {

    private fun issuesOf(code: String): List<Issue> = Validator.validate(Parser(code).parse())

    @Test
    fun refInUnreachableSceneCountsAsUse() {
        val src = """
            scene start:
              set hp = 100
              text: "开始"
              end
            scene dead:
              text: "血量 {hp}"
              end
        """.trimIndent()
        val issues = issuesOf(src)

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertTrue(unused.isEmpty(), "dead 场景虽不可达，但其文本引用 hp 应视为使用，不应报 UNUSED_VAR")

        val unreachable = issues.filter { it.code == "UNREACHABLE" }
        assertEquals(1, unreachable.size, "应恰好报告 1 条 UNREACHABLE")
        assertEquals("dead", unreachable[0].sceneId, "UNREACHABLE 的 sceneId 应为 dead")
        assertEquals(5, unreachable[0].line, "UNREACHABLE 的行号应为 dead 场景起始行 5")
        assertEquals(Severity.WARNING, unreachable[0].severity, "UNREACHABLE 严重级别应为 WARNING")
    }

    @Test
    fun assignedInUnreachableSceneSuppressesUninit() {
        val src = """
            scene start:
              text: "{hp}"
              end
            scene dead:
              set hp = 100
              end
        """.trimIndent()
        val issues = issuesOf(src)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertTrue(uninit.isEmpty(), "collectAssignedVars 全局收集，dead 场景的 set hp 应抑制 UNINIT_VAR")

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertTrue(unused.isEmpty(), "hp 在 start 的文本中被引用，不应报 UNUSED_VAR")

        val unreachable = issues.filter { it.code == "UNREACHABLE" }
        assertEquals(1, unreachable.size, "应恰好报告 1 条 UNREACHABLE")
        assertEquals("dead", unreachable[0].sceneId, "UNREACHABLE 的 sceneId 应为 dead")
        assertEquals(Severity.WARNING, unreachable[0].severity, "UNREACHABLE 严重级别应为 WARNING")
    }

    @Test
    fun unusedSetInUnreachableSceneStillWarns() {
        val src = """
            scene start:
              text: "开始"
              end
            scene dead:
              set ghost = 1
              end
        """.trimIndent()
        val issues = issuesOf(src)

        val unreachable = issues.filter { it.code == "UNREACHABLE" }
        assertEquals(1, unreachable.size, "应恰好报告 1 条 UNREACHABLE")
        assertEquals("dead", unreachable[0].sceneId, "UNREACHABLE 的 sceneId 应为 dead")
        assertEquals(Severity.WARNING, unreachable[0].severity, "UNREACHABLE 严重级别应为 WARNING")

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unused.size, "ghost 从未被使用，应恰好报告 1 条 UNUSED_VAR")
        assertEquals("dead", unused[0].sceneId, "UNUSED_VAR 的 sceneId 应为 dead")
        assertEquals(5, unused[0].line, "UNUSED_VAR 的行号应为 ghost 首次 set 的行 5")
        assertEquals(Severity.WARNING, unused[0].severity, "UNUSED_VAR 严重级别应为 WARNING")
        assertTrue(unused[0].message.contains("ghost"), "UNUSED_VAR 消息应包含变量名 ghost")
    }
}