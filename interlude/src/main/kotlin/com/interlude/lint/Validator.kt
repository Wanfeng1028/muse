
package com.interlude.lint

import com.interlude.dsl.Choice
import com.interlude.dsl.Expr
import com.interlude.dsl.IntLit
import com.interlude.dsl.Jump
import com.interlude.dsl.Not
import com.interlude.dsl.Binary
import com.interlude.dsl.Binary.Op
import com.interlude.dsl.Neg
import com.interlude.dsl.Scene
import com.interlude.dsl.SetVar
import com.interlude.dsl.Statement
import com.interlude.dsl.Story
import com.interlude.dsl.StrLit
import com.interlude.dsl.Text
import com.interlude.dsl.VarRef
import com.interlude.dsl.End
import com.interlude.dsl.extractPlaceholders

enum class Severity { ERROR, WARNING }

data class Issue(
    val severity: Severity,
    val code: String,
    val message: String,
    val sceneId: String,
    val line: Int
)

object Validator {

    fun validate(story: Story): List<Issue> {
        val issues = mutableListOf<Issue>()
        val sceneIds = story.scenes.map { it.id }.toSet()

        val assignedVars = collectAssignedVars(story)

        for (scene in story.scenes) {
            checkTargets(scene, sceneIds, issues)
            checkDeadEnd(scene, issues)
            checkVars(scene, assignedVars, issues)
            checkConditions(scene, issues)
        }

        checkUnreachable(story, issues)

        checkUnusedVars(story, issues)

        return issues.sortedWith(compareBy({ it.severity.ordinal }, { it.line }))
    }

    private fun checkUnusedVars(story: Story, issues: MutableList<Issue>) {
        val used = mutableSetOf<String>()
        for (scene in story.scenes) {
            for (st in scene.statements) {
                when (st) {
                    is Text -> used.addAll(extractPlaceholders(st.value))
                    is SetVar -> used.addAll(collectVarRefs(st.expr))
                    is Choice -> {
                        val cond = st.condition
                        if (cond != null) used.addAll(collectVarRefs(cond))
                    }
                    is Jump -> {
                        val cond = st.condition
                        if (cond != null) used.addAll(collectVarRefs(cond))
                    }
                    else -> {}
                }
            }
        }

        val reported = mutableSetOf<String>()
        for (scene in story.scenes) {
            for (st in scene.statements) {
                if (st is SetVar && st.name !in used && st.name !in reported) {
                    reported.add(st.name)
                    issues.add(
                    Issue(
                    Severity.WARNING,
                    "UNUSED_VAR",
                    "变量 '${st.name}' 被 set 赋值后从未使用",
                    scene.id,
                    st.line
                    )
                    )
                }
            }
        }
    }

    private fun collectAssignedVars(story: Story): Set<String> {
        val result = mutableSetOf<String>()
        for (scene in story.scenes) {
            for (st in scene.statements) {
                if (st is SetVar) result.add(st.name)
            }
        }
        return result
    }

    private fun checkTargets(scene: Scene, sceneIds: Set<String>, issues: MutableList<Issue>) {
        for (st in scene.statements) {
            when (st) {
                is Choice -> {
                    if (st.target !in sceneIds) {
                        issues.add(
                            Issue(
                                Severity.ERROR,
                                "UNDEFINED_TARGET",
                                "choice 的目标场景 '${st.target}' 不存在",
                                scene.id,
                                st.line
                            )
                        )
                    }
                }
                is Jump -> {
                    if (st.target !in sceneIds) {
                        issues.add(
                            Issue(
                                Severity.ERROR,
                                "UNDEFINED_TARGET",
                                "jump 的目标场景 '${st.target}' 不存在",
                                scene.id,
                                st.line
                            )
                        )
                    }
                }
                else -> {}
            }
        }
    }

    private fun checkDeadEnd(scene: Scene, issues: MutableList<Issue>) {
        var hasExit = false
        var hasEnd = false
        for (st in scene.statements) {
            when (st) {
                is Choice, is Jump -> hasExit = true
                is End -> hasEnd = true
                else -> {}
            }
        }
        if (!hasExit && !hasEnd) {
            issues.add(
                Issue(
                    Severity.WARNING,
                    "DEAD_END",
                    "场景 '${scene.id}' 没有任何出边且未以 end 结尾",
                    scene.id,
                    scene.line
                )
            )
        }
    }

    private fun checkVars(scene: Scene, assigned: Set<String>, issues: MutableList<Issue>) {
        for (st in scene.statements) {
            when (st) {
                is Text -> {
                    for (name in extractPlaceholders(st.value)) {
                        if (name !in assigned) {
                            issues.add(
                                Issue(
                                    Severity.ERROR,
                                    "UNINIT_VAR",
                                    "文本占位符引用了从未被 set 的变量 '$name'",
                                    scene.id,
                                    st.line
                                )
                            )
                        }
                    }
                }
                is SetVar -> {
                    collectVarRefs(st.expr).forEach { name ->
                        if (name !in assigned) {
                            issues.add(
                                Issue(
                                    Severity.ERROR,
                                    "UNINIT_VAR",
                                    "赋值表达式引用了从未被 set 的变量 '$name'",
                                    scene.id,
                                    st.line
                                )
                            )
                        }
                    }
                }
                is Choice -> {
                    st.condition?.let { c ->
                        collectVarRefs(c).forEach { name ->
                            if (name !in assigned) {
                                issues.add(
                                    Issue(
                                        Severity.ERROR,
                                        "UNINIT_VAR",
                                        "choice 条件引用了从未被 set 的变量 '$name'",
                                        scene.id,
                                        st.line
                                    )
                                )
                            }
                        }
                    }
                }
                is Jump -> {
                    st.condition?.let { c ->
                        collectVarRefs(c).forEach { name ->
                            if (name !in assigned) {
                                issues.add(
                                    Issue(
                                        Severity.ERROR,
                                        "UNINIT_VAR",
                                        "jump 条件引用了从未被 set 的变量 '$name'",
                                        scene.id,
                                        st.line
                                    )
                                )
                            }
                        }
                    }
                }
                else -> {}
            }
        }
    }

    private fun collectVarRefs(expr: Expr): Set<String> {
        val result = mutableSetOf<String>()
        fun walk(e: Expr) {
            when (e) {
                is VarRef -> result.add(e.name)
                is Binary -> {
                    walk(e.left)
                    walk(e.right)
                }
                is Not -> walk(e.operand)
                is Neg -> walk(e.operand)
                else -> {}
            }
        }
        walk(expr)
        return result
    }

    private fun checkConditions(scene: Scene, issues: MutableList<Issue>) {
        for (st in scene.statements) {
            val cond: Expr? = when (st) {
                is Choice -> st.condition
                is Jump -> st.condition
                else -> null
            }
            if (cond != null) {
                val value = tryConstEval(cond)
                if (value is Boolean && !value) {
                    issues.add(
                        Issue(
                            Severity.WARNING,
                            "ALWAYS_FALSE",
                            "条件表达式恒为 false",
                            scene.id,
                            st.line
                        )
                    )
                }
            }
        }
    }

    private fun checkUnreachable(story: Story, issues: MutableList<Issue>) {
        if (story.scenes.isEmpty()) return
        val entry = story.scenes.first()
        val sceneIds = story.scenes.map { it.id }.toSet()
        val reachable = mutableSetOf<String>()
        val queue = ArrayDeque<String>()
        reachable.add(entry.id)
        queue.add(entry.id)
        val byId = story.scenes.associateBy { it.id }

        while (queue.isNotEmpty()) {
            val id = queue.removeFirst()
            val scene = byId[id] ?: continue
            for (st in scene.statements) {
                val target = when (st) {
                    is Choice -> st.target
                    is Jump -> st.target
                    else -> null
                }
                if (target != null && target in sceneIds && target !in reachable) {
                    reachable.add(target)
                    queue.add(target)
                }
            }
        }

        for (scene in story.scenes) {
            if (scene.id !in reachable) {
                issues.add(
                    Issue(
                        Severity.WARNING,
                        "UNREACHABLE",
                        "场景 '${scene.id}' 从入口不可达",
                        scene.id,
                        scene.line
                    )
                )
            }
        }
    }

    // 仅对纯字面量表达式求值；含 VarRef 返回 null
    private fun tryConstEval(expr: Expr): Any? {
        return when (expr) {
            is IntLit -> expr.value
            is StrLit -> expr.value
            is VarRef -> null
            is Not -> {
                val v = tryConstEval(expr.operand) ?: return null
                if (v is Boolean) !v else null
            }
            is Neg -> {
                val v = tryConstEval(expr.operand) ?: return null
                if (v is Long) -v else null
            }
            is Binary -> {
                val l = tryConstEval(expr.left) ?: return null
                val r = tryConstEval(expr.right) ?: return null
                evalBinary(expr.op, l, r)
            }
        }
    }

    private fun evalBinary(op: Op, l: Any, r: Any): Any? {
        // AST 的整数字面量为 Long，这里统一按 Long 做算术/比较
        return when (op) {
            Op.PLUS -> {
                when {
                    l is Long && r is Long -> l + r
                    l is String && r is String -> l + r
                    else -> null
                }
            }
            Op.MINUS -> if (l is Long && r is Long) l - r else null
            Op.TIMES -> if (l is Long && r is Long) l * r else null
            Op.DIV -> if (l is Long && r is Long && r != 0L) l / r else null
            Op.GT -> if (l is Long && r is Long) l > r else null
            Op.LT -> if (l is Long && r is Long) l < r else null
            Op.GTE -> if (l is Long && r is Long) l >= r else null
            Op.LTE -> if (l is Long && r is Long) l <= r else null
            Op.EQ -> l == r
            Op.NEQ -> l != r
            Op.AND -> if (l is Boolean && r is Boolean) l && r else null
            Op.OR -> if (l is Boolean && r is Boolean) l || r else null
        }
    }
}
