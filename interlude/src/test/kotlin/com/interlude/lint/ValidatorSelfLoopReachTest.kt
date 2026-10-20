package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ValidatorSelfLoopReachTest {

    private fun codes(issues: List<Issue>): List<String> = issues.map { it.code }

    @Test
    fun selfJumpReachableNoIssues() {
        val source = buildString {
            append("scene start:\n")
            append("  jump -> start\n")
        }
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        assertTrue(
            issues.isEmpty(),
            "自循环 jump 场景应无任何问题，实际为 ${codes(issues)}"
        )
    }

    @Test
    fun selfChoiceReachable() {
        val source = buildString {
            append("scene start:\n")
            append("  choice \"再来\" -> start\n")
            append("  end\n")
        }
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        assertFalse(
            issues.any { it.code == "UNREACHABLE" },
            "自循环 choice 的目标即入口自身，应可达，不应报 UNREACHABLE"
        )
        assertFalse(
            issues.any { it.code == "DEAD_END" },
            "场景含 choice 出边且有 end，不应报 DEAD_END"
        )
    }

    @Test
    fun cycleOfTwoScenesReachable() {
        val source = buildString {
            append("scene start:\n")
            append("  jump -> b\n")
            append("scene b:\n")
            append("  jump -> start\n")
        }
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        assertFalse(
            issues.any { it.code == "UNREACHABLE" },
            "两场景互跳闭环中 b 可从 start 到达，不应报 UNREACHABLE"
        )
        assertFalse(
            issues.any { it.code == "DEAD_END" && it.sceneId == "b" },
            "场景 b 有 jump 出口，不应报 DEAD_END"
        )
    }
}