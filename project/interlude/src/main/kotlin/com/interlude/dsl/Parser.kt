
package com.interlude.dsl

class ParseError(val line: Int, message: String) : Exception("第 $line 行: $message")

/**
 * 「幕间 Interlude」叙事 DSL 的手写递归下降解析器。
 *
 * 语法（v1）：
 *   scene <id>:
 *     text: "..."
 *     set <name> = <expr>
 *     choice "<label>" -> <target> [if <cond>]
 *     jump -> <target> [if <cond>]
 *     end
 *
 * 缩进固定为 2 空格；第一条 scene 为入口。
 */
class Parser(source: String) {

    private data class Line(val number: Int, val indent: Int, val content: String)

    private val lines: List<Line> = tokenizeLines(source)
    private var pos: Int = 0

    fun parse(): Story {
        val scenes = mutableListOf<Scene>()
        while (pos < lines.size) {
            val line = lines[pos]
            if (line.indent != 0) {
                throw ParseError(line.number, "顶层语句不允许缩进")
            }
            if (!line.content.startsWith("scene ")) {
                throw ParseError(line.number, "期望 'scene <id>:' 声明，实际为 '${line.content}'")
            }
            scenes += parseScene(line)
        }
        if (scenes.isEmpty()) {
            throw ParseError(1, "剧本为空，至少需要一个 scene")
        }
        return Story(scenes)
    }

    private fun parseScene(header: Line): Scene {
        val rest = header.content.removePrefix("scene ").trim()
        if (!rest.endsWith(":")) {
            throw ParseError(header.number, "scene 声明缺少冒号: '${header.content}'")
        }
        val id = rest.dropLast(1).trim()
        if (!isValidId(id)) {
            throw ParseError(header.number, "非法的 scene 标识符 '$id'")
        }
        pos++

        val statements = mutableListOf<Statement>()
        while (pos < lines.size) {
            val line = lines[pos]
            if (line.indent == 0) break
            if (line.indent != 2) {
                throw ParseError(line.number, "缩进必须为 2 个空格，实际为 ${line.indent}")
            }
            statements += parseStatement(line)
        }
        return Scene(id, header.number, statements)
    }

    private fun parseStatement(line: Line): Statement {
        val c = line.content
        return when {
            c.startsWith("text:") -> parseText(line)
            c.startsWith("text ") -> throw ParseError(line.number, "text 语句缺少冒号: '$c'")
            c.startsWith("set ") -> parseSet(line)
            c.startsWith("set") -> throw ParseError(line.number, "set 语句格式错误: '$c'")
            c.startsWith("choice ") -> parseChoice(line)
            c.startsWith("choice") -> throw ParseError(line.number, "choice 语句格式错误: '$c'")
            c.startsWith("jump ") -> parseJump(line)
            c.startsWith("jump") -> throw ParseError(line.number, "jump 语句格式错误: '$c'")
            c == "end" -> {
                pos++
                End(line.number)
            }
            else -> throw ParseError(line.number, "未知语句: '$c'")
        }
    }

    private fun parseText(line: Line): Statement {
        val body = line.content.removePrefix("text:").trim()
        val cursor = Cursor(body, line.number)
        val value = cursor.readStringLiteral()
        cursor.skipSpaces()
        if (!cursor.eof()) {
            throw ParseError(line.number, "text 语句存在多余内容: '${cursor.remaining()}'")
        }
        pos++
        return Text(line.number, value)
    }

    private fun parseSet(line: Line): Statement {
        val body = line.content.removePrefix("set ").trim()
        val eq = body.indexOf('=')
        if (eq < 0) throw ParseError(line.number, "set 语句缺少 '='")
        val name = body.substring(0, eq).trim()
        if (!isValidId(name)) {
            throw ParseError(line.number, "非法的变量名 '$name'")
        }
        val exprSource = body.substring(eq + 1).trim()
        if (exprSource.isEmpty()) {
            throw ParseError(line.number, "set 语句缺少表达式")
        }
        val expr = ExprParser(exprSource, line.number).parse()
        pos++
        return SetVar(line.number, name, expr)
    }

    private fun parseChoice(line: Line): Statement {
        val body = line.content.removePrefix("choice ").trim()
        val cursor = Cursor(body, line.number)
        val label = cursor.readStringLiteral()
        cursor.skipSpaces()
        cursor.expectArrow()
        cursor.skipSpaces()
        val target = cursor.readIdentifier()
        if (target.isEmpty() || !isValidId(target)) {
            throw ParseError(line.number, "非法的 choice 目标 '$target'")
        }
        val cond = cursor.readOptionalCondition()
        pos++
        return Choice(line.number, label, target, cond)
    }

    private fun parseJump(line: Line): Statement {
        val body = line.content.removePrefix("jump ").trim()
        val cursor = Cursor(body, line.number)
        cursor.expectArrow()
        cursor.skipSpaces()
        val target = cursor.readIdentifier()
        if (target.isEmpty() || !isValidId(target)) {
            throw ParseError(line.number, "非法的 jump 目标 '$target'")
        }
        val cond = cursor.readOptionalCondition()
        pos++
        return Jump(line.number, target, cond)
    }

    // ---------- 词法辅助 ----------

    private class Cursor(private val src: String, private val line: Int) {
        private var i = 0

        fun eof(): Boolean = i >= src.length
        fun remaining(): String = src.substring(i)

        fun skipSpaces() {
            while (i < src.length && src[i] == ' ') i++
        }

        fun readStringLiteral(): String {
            if (i >= src.length || src[i] != '"') {
                throw ParseError(line, "期望字符串字面量起始 '\"'")
            }
            i++
            val sb = StringBuilder()
            while (i < src.length) {
                val ch = src[i]
                when (ch) {
                    '\\' -> {
                        i++
                        if (i >= src.length) throw ParseError(line, "字符串未闭合")
                        when (val esc = src[i]) {
                            '"' -> sb.append('"')
                            '\\' -> sb.append('\\')
                            'n' -> sb.append('\n')
                            't' -> sb.append('\t')
                            else -> sb.append(esc)
                        }
                        i++
                    }
                    '"' -> {
                        i++
                        return sb.toString()
                    }
                    else -> {
                        sb.append(ch)
                        i++
                    }
                }
            }
            throw ParseError(line, "字符串字面量未闭合")
        }

        fun readIdentifier(): String {
            val start = i
            while (i < src.length && (src[i].isLetterOrDigit() || src[i] == '_')) i++
            return src.substring(start, i)
        }

        fun expectArrow() {
            if (i + 1 >= src.length || src[i] != '-' || src[i + 1] != '>') {
                throw ParseError(line, "期望 '->'，实际为 '${remaining()}'")
            }
            i += 2
        }

        fun readOptionalCondition(): Expr? {
            skipSpaces()
            if (eof()) return null
            if (!src.startsWith("if", i) || (i + 2 < src.length && (src[i + 2].isLetterOrDigit() || src[i + 2] == '_'))) {
                throw ParseError(line, "语句存在多余内容: '${remaining()}'")
            }
            i += 2
            skipSpaces()
            val exprText = src.substring(i)
            if (exprText.isEmpty()) {
                throw ParseError(line, "if 缺少条件表达式")
            }
            i = src.length
            return ExprParser(exprText, line).parse()
        }
    }

    private fun tokenizeLines(source: String): List<Line> {
        val result = mutableListOf<Line>()
        var lineNo = 0
        for (raw in source.split('\n')) {
            lineNo++
            val noCr = raw.trimEnd('\r')
            val indent = noCr.takeWhile { it == ' ' }.length
            val content = noCr.substring(indent)
            if (content.isEmpty()) continue
            if (content.startsWith("#")) continue
            result += Line(lineNo, indent, content)
        }
        return result
    }

    private fun isValidId(id: String): Boolean {
        if (id.isEmpty()) return false
        if (!(id[0].isLetter() || id[0] == '_')) return false
        return id.all { it.isLetterOrDigit() || it == '_' }
    }

    // ---------- 表达式解析 ----------

    private class ExprParser(private val src: String, private val line: Int) {
        private var i = 0

        fun parse(): Expr {
            val e = parseOr()
            skipSpaces()
            if (i < src.length) {
                throw ParseError(line, "表达式中存在无法解析的内容: '${src.substring(i)}'")
            }
            return e
        }

        private fun parseOr(): Expr {
            var left = parseAnd()
            while (true) {
                skipSpaces()
                if (matchKeyword("or")) {
                    val right = parseAnd()
                    left = Binary(Binary.Op.OR, left, right)
                } else break
            }
            return left
        }

        private fun parseAnd(): Expr {
            var left = parseComparison()
            while (true) {
                skipSpaces()
                if (matchKeyword("and")) {
                    val right = parseComparison()
                    left = Binary(Binary.Op.AND, left, right)
                } else break
            }
            return left
        }

        private fun parseComparison(): Expr {
            var left = parseAdditive()
            while (true) {
                skipSpaces()
                val op = peekComparisonOp() ?: break
                consumeComparisonOp(op)
                val right = parseAdditive()
                left = Binary(op, left, right)
            }
            return left
        }

        private fun parseAdditive(): Expr {
            var left = parseMultiplicative()
            while (true) {
                skipSpaces()
                if (i >= src.length) break
                val ch = src[i]
                if (ch == '+') {
                    i++
                    left = Binary(Binary.Op.PLUS, left, parseMultiplicative())
                } else if (ch == '-') {
                    i++
                    left = Binary(Binary.Op.MINUS, left, parseMultiplicative())
                } else break
            }
            return left
        }

        private fun parseMultiplicative(): Expr {
            var left = parseUnary()
            while (true) {
                skipSpaces()
                if (i >= src.length) break
                val ch = src[i]
                if (ch == '*') {
                    i++
                    left = Binary(Binary.Op.TIMES, left, parseUnary())
                } else if (ch == '/') {
                    i++
                    left = Binary(Binary.Op.DIV, left, parseUnary())
                } else break
            }
            return left
        }

        private fun parseUnary(): Expr {
            skipSpaces()
            if (matchKeyword("not")) {
                return Not(parseUnary())
            }
            if (i < src.length && src[i] == '-') {
                i++
                return Neg(parseUnary())
            }
            return parseAtom()
        }

        private fun parseAtom(): Expr {
            skipSpaces()
            if (i >= src.length) throw ParseError(line, "表达式意外结束")
            val ch = src[i]
            if (ch == '(') {
                i++
                val e = parseOr()
                skipSpaces()
                if (i >= src.length || src[i] != ')') {
                    throw ParseError(line, "缺少右括号 ')'")
                }
                i++
                return e
            }
            if (ch == '"') {
                return StrLit(readStringLiteral())
            }
            if (ch.isDigit()) {
                val start = i
                while (i < src.length && src[i].isDigit()) i++
                return IntLit(src.substring(start, i).toLong())
            }
            if (ch.isLetter() || ch == '_') {
                val start = i
                while (i < src.length && (src[i].isLetterOrDigit() || src[i] == '_')) i++
                val name = src.substring(start, i)
                return when (name) {
                    "true" -> IntLit(1)
                    "false" -> IntLit(0)
                    else -> VarRef(name)
                }
            }
            throw ParseError(line, "无法解析的表达式字符 '$ch'")
        }

        private fun peekComparisonOp(): Binary.Op? {
            if (i >= src.length) return null
            if (src.startsWith(">=", i)) return Binary.Op.GTE
            if (src.startsWith("<=", i)) return Binary.Op.LTE
            if (src.startsWith("==", i)) return Binary.Op.EQ
            if (src.startsWith("!=", i)) return Binary.Op.NEQ
            return when (src[i]) {
                '>' -> Binary.Op.GT
                '<' -> Binary.Op.LT
                else -> null
            }
        }

        private fun consumeComparisonOp(op: Binary.Op) {
            i += when (op) {
                Binary.Op.GTE, Binary.Op.LTE, Binary.Op.EQ, Binary.Op.NEQ -> 2
                else -> 1
            }
        }

        private fun matchKeyword(kw: String): Boolean {
            if (!src.startsWith(kw, i)) return false
            val end = i + kw.length
            if (end < src.length && (src[end].isLetterOrDigit() || src[end] == '_')) return false
            if (i > 0 && (src[i - 1].isLetterOrDigit() || src[i - 1] == '_')) return false
            i = end
            return true
        }

        private fun readStringLiteral(): String {
            if (src[i] != '"') throw ParseError(line, "期望字符串字面量")
            i++
            val sb = StringBuilder()
            while (i < src.length) {
                val ch = src[i]
                when (ch) {
                    '\\' -> {
                        i++
                        if (i >= src.length) throw ParseError(line, "字符串未闭合")
                        when (val esc = src[i]) {
                            '"' -> sb.append('"')
                            '\\' -> sb.append('\\')
                            'n' -> sb.append('\n')
                            't' -> sb.append('\t')
                            else -> sb.append(esc)
                        }
                        i++
                    }
                    '"' -> {
                        i++
                        return sb.toString()
                    }
                    else -> {
                        sb.append(ch)
                        i++
                    }
                }
            }
            throw ParseError(line, "字符串字面量未闭合")
        }

        private fun skipSpaces() {
            while (i < src.length && src[i] == ' ') i++
        }
    }
}

/** 从 text 中提取所有 {name} 占位符，按出现顺序，去重保留首次出现。 */
fun extractPlaceholders(text: String): List<String> {
    val result = LinkedHashSet<String>()
    var i = 0
    while (i < text.length) {
        val ch = text[i]
        if (ch == '\\' && i + 1 < text.length) {
            i += 2
            continue
        }
        if (ch == '{') {
            val end = text.indexOf('}', i + 1)
            if (end < 0) break
            val name = text.substring(i + 1, end)
            if (name.isNotEmpty() && isPlaceholderId(name)) {
                result += name
            }
            i = end + 1
        } else {
            i++
        }
    }
    return result.toList()
}

private fun isPlaceholderId(name: String): Boolean {
    if (name.isEmpty()) return false
    if (!(name[0].isLetter() || name[0] == '_')) return false
    return name.all { it.isLetterOrDigit() || it == '_' }
}
