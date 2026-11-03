
package com.interlude.dsl

data class Story(val scenes: List<Scene>) {
    val entry: Scene? get() = scenes.firstOrNull()
    fun sceneById(id: String): Scene? = scenes.firstOrNull { it.id == id }
}

data class Scene(val id: String, val line: Int, val statements: List<Statement>)

sealed interface Statement { val line: Int }

data class Text(override val line: Int, val value: String) : Statement
data class SetVar(override val line: Int, val name: String, val expr: Expr) : Statement
data class Choice(override val line: Int, val label: String, val target: String, val condition: Expr?) : Statement
data class Jump(override val line: Int, val target: String, val condition: Expr?) : Statement
data class End(override val line: Int) : Statement

sealed interface Expr
data class IntLit(val value: Long) : Expr
data class StrLit(val value: String) : Expr
data class VarRef(val name: String) : Expr
data class Binary(val op: Op, val left: Expr, val right: Expr) : Expr {
    enum class Op { PLUS, MINUS, TIMES, DIV, GT, LT, GTE, LTE, EQ, NEQ, AND, OR }
}
data class Not(val operand: Expr) : Expr
data class Neg(val operand: Expr) : Expr
