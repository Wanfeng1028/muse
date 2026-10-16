package com.interlude.replay

/**
 * 对局日志解析异常。message 中会携带事件序号（如 events[3]）或字段名，便于定位问题。
 */
class SessionLogParseException(message: String) : Exception(message)

/**
 * 对局日志 JSON 解析入口。手写递归下降解析器，不依赖任何第三方 JSON 库。
 */
object SessionLog {

    /**
     * 解析对局日志 JSON 文本，返回事件列表。
     * 第一个元素恒为由顶层 "session" 对象合成的 [SessionStart]。
     *
     * @param text 对局日志 JSON 文本
     * @return 事件列表，首元素为 [SessionStart]
     * @throws SessionLogParseException 顶层结构不合法、字段缺失/类型错误、未知 type、
     *         JSON 语法错误时抛出；message 含事件序号、字段名或 "JSON" 及出错位置。
     */
    fun parse(text: String): List<SessionEvent> {
        val parser = JsonParser(text)
        val root = parser.parse()
        if (root !is JsonObject) {
            throw SessionLogParseException("JSON 顶层必须是 object，实际为 ${root.typeName()}")
        }

        val sessionNode = root.fields["session"]
            ?: throw SessionLogParseException("缺少顶层字段 session")
        if (sessionNode !is JsonObject) {
            throw SessionLogParseException("顶层字段 session 必须是 object，实际为 ${sessionNode.typeName()}")
        }

        val eventsNode = root.fields["events"]
            ?: throw SessionLogParseException("缺少顶层字段 events")
        if (eventsNode !is JsonArray) {
            throw SessionLogParseException("顶层字段 events 必须是 array，实际为 ${eventsNode.typeName()}")
        }

        val sessionId = requireString(sessionNode, "id", "session.id")
        val script = requireString(sessionNode, "script", "session.script")
        val startedAt = requireString(sessionNode, "startedAt", "session.startedAt")
        val players = sessionNode.fields["players"]?.let {
            if (it !is JsonNumber || it.isDouble) {
                throw SessionLogParseException("字段 session.players 必须是 int，实际为 ${it.typeName()}")
            }
            it.longValue.toInt()
        } ?: 1

        val result = ArrayList<SessionEvent>(eventsNode.items.size + 1)
        result.add(SessionStart(sessionId, script, players, startedAt))

        eventsNode.items.forEachIndexed { index, node ->
            result.add(parseEvent(node, index))
        }
        return result
    }

    /** 解析单个 events[i] 事件节点。 */
    private fun parseEvent(node: JsonValue, index: Int): SessionEvent {
        val prefix = "events[$index]"
        if (node !is JsonObject) {
            throw SessionLogParseException("$prefix 必须是 object，实际为 ${node.typeName()}")
        }
        val type = node.fields["type"]
        if (type == null) {
            throw SessionLogParseException("$prefix 缺少必需字段 type")
        }
        if (type !is JsonString) {
            throw SessionLogParseException("$prefix 字段 type 必须是 string，实际为 ${type.typeName()}")
        }

        return when (type.value) {
            "scene" -> SceneEnter(
                sceneId = requireString(node, "scene", "$prefix.scene"),
                at = requireString(node, "at", "$prefix.at"),
            )

            "choice" -> ChoiceMade(
                sceneId = requireString(node, "scene", "$prefix.scene"),
                label = requireString(node, "label", "$prefix.label"),
                target = requireString(node, "target", "$prefix.target"),
                alternatives = parseAlternatives(node, prefix),
                at = requireString(node, "at", "$prefix.at"),
            )

            "vote" -> VoteCast(
                voter = requireString(node, "voter", "$prefix.voter"),
                target = requireString(node, "target", "$prefix.target"),
                round = requireInt(node, "round", "$prefix.round"),
                at = requireString(node, "at", "$prefix.at"),
            )

            "elimination" -> Elimination(
                player = requireString(node, "player", "$prefix.player"),
                reason = requireString(node, "reason", "$prefix.reason"),
                round = requireInt(node, "round", "$prefix.round"),
                at = requireString(node, "at", "$prefix.at"),
            )

            "note" -> KeyMoment(
                note = requireString(node, "note", "$prefix.note"),
                sceneId = optionalString(node, "scene", "$prefix.scene"),
                at = requireString(node, "at", "$prefix.at"),
            )

            "end" -> SessionEnd(
                outcome = requireString(node, "outcome", "$prefix.outcome"),
                winner = optionalString(node, "winner", "$prefix.winner"),
                at = requireString(node, "at", "$prefix.at"),
            )

            else -> throw SessionLogParseException("$prefix 未知的事件 type：\"${type.value}\"")
        }
    }

    /** 解析 choice 的 alternatives，缺省返回空列表。 */
    private fun parseAlternatives(node: JsonObject, prefix: String): List<Alternative> {
        val altNode = node.fields["alternatives"] ?: return emptyList()
        if (altNode !is JsonArray) {
            throw SessionLogParseException("$prefix.alternatives 必须是 array，实际为 ${altNode.typeName()}")
        }
        return altNode.items.mapIndexed { i, item ->
            val altPrefix = "$prefix.alternatives[$i]"
            if (item !is JsonObject) {
                throw SessionLogParseException("$altPrefix 必须是 object，实际为 ${item.typeName()}")
            }
            Alternative(
                label = requireString(item, "label", "$altPrefix.label"),
                target = requireString(item, "target", "$altPrefix.target"),
            )
        }
    }

    /** 取必需 string 字段，缺失或类型错误时抛异常（message 含字段名）。 */
    private fun requireString(node: JsonObject, key: String, fieldName: String): String {
        val value = node.fields[key]
            ?: throw SessionLogParseException("缺少必需字段 $fieldName")
        if (value !is JsonString) {
            throw SessionLogParseException("字段 $fieldName 必须是 string，实际为 ${value.typeName()}")
        }
        return value.value
    }

    /** 取可选 string 字段，缺省或 null 返回 null；类型错误抛异常。 */
    private fun optionalString(node: JsonObject, key: String, fieldName: String): String? {
        val value = node.fields[key] ?: return null
        if (value is JsonNull) return null
        if (value !is JsonString) {
            throw SessionLogParseException("字段 $fieldName 必须是 string 或 null，实际为 ${value.typeName()}")
        }
        return value.value
    }

    /** 取必需 int 字段，必须是整数（非 Double），否则抛异常。 */
    private fun requireInt(node: JsonObject, key: String, fieldName: String): Int {
        val value = node.fields[key]
            ?: throw SessionLogParseException("缺少必需字段 $fieldName")
        if (value !is JsonNumber || value.isDouble) {
            throw SessionLogParseException("字段 $fieldName 必须是 int，实际为 ${value.typeName()}")
        }
        return value.longValue.toInt()
    }
}

/* -------------------------------------------------------------------------- */
/*                         手写 JSON 递归下降解析器                             */
/* -------------------------------------------------------------------------- */

/** JSON 值基类，[typeName] 用于拼装可读的错误信息。 */
private sealed class JsonValue {
    abstract fun typeName(): String
}

private object JsonNull : JsonValue() {
    override fun typeName(): String = "null"
}

private data class JsonBool(val value: Boolean) : JsonValue() {
    override fun typeName(): String = "boolean"
}

/** 数字节点。[isDouble] 为 true 表示带小数点或指数，[longValue] 保存截断后的整数值。 */
private data class JsonNumber(val isDouble: Boolean, val longValue: Long) : JsonValue() {
    override fun typeName(): String = if (isDouble) "double" else "int"
}

private data class JsonString(val value: String) : JsonValue() {
    override fun typeName(): String = "string"
}

private data class JsonArray(val items: List<JsonValue>) : JsonValue() {
    override fun typeName(): String = "array"
}

private data class JsonObject(val fields: Map<String, JsonValue>) : JsonValue() {
    override fun typeName(): String = "object"
}

/**
 * 手写递归下降 JSON 解析器。支持 object / array / string（含转义）/ number / true / false / null。
 * 语法错误抛出 [SessionLogParseException]，message 含 "JSON" 与字符偏移定位。
 */
private class JsonParser(private val text: String) {

    private var pos = 0

    /** 解析整段文本，要求恰好消费完所有输入。 */
    fun parse(): JsonValue {
        skipWhitespace()
        if (pos >= text.length) fail("输入为空")
        val value = parseValue()
        skipWhitespace()
        if (pos < text.length) {
            fail("JSON 结尾存在多余字符")
        }
        return value
    }

    private fun parseValue(): JsonValue {
        skipWhitespace()
        if (pos >= text.length) fail("意外到达输入末尾")
        return when (val c = text[pos]) {
            '{' -> parseObject()
            '[' -> parseArray()
            '"' -> JsonString(parseString())
            't' -> parseLiteral("true", JsonBool(true))
            'f' -> parseLiteral("false", JsonBool(false))
            'n' -> parseLiteral("null", JsonNull)
            '-', in '0'..'9' -> parseNumber()
            else -> fail("JSON 出现非法字符 '$c'")
        }
    }

    private fun parseObject(): JsonObject {
        expect('{')
        val fields = LinkedHashMap<String, JsonValue>()
        skipWhitespace()
        if (peek() == '}') {
            pos++
            return JsonObject(fields)
        }
        while (true) {
            skipWhitespace()
            if (peek() != '"') fail("JSON object 的键必须是字符串")
            val key = parseString()
            skipWhitespace()
            expect(':')
            val value = parseValue()
            fields[key] = value
            skipWhitespace()
            when (peek()) {
                ',' -> { pos++ }
                '}' -> { pos++; return JsonObject(fields) }
                else -> fail("JSON object 缺少 ',' 或 '}'")
            }
        }
    }

    private fun parseArray(): JsonArray {
        expect('[')
        val items = ArrayList<JsonValue>()
        skipWhitespace()
        if (peek() == ']') {
            pos++
            return JsonArray(items)
        }
        while (true) {
            val value = parseValue()
            items.add(value)
            skipWhitespace()
            when (peek()) {
                ',' -> { pos++ }
                ']' -> { pos++; return JsonArray(items) }
                else -> fail("JSON array 缺少 ',' 或 ']'")
            }
        }
    }

    private fun parseString(): String {
        expect('"')
        val sb = StringBuilder()
        while (true) {
            if (pos >= text.length) fail("JSON 字符串未闭合")
            when (val c = text[pos++]) {
                '"' -> return sb.toString()
                '\\' -> sb.append(parseEscape())
                else -> {
                    if (c.code < 0x20) fail("JSON 字符串中出现未转义的控制字符")
                    sb.append(c)
                }
            }
        }
    }

    private fun parseEscape(): Char {
        if (pos >= text.length) fail("JSON 转义序列不完整")
        return when (val e = text[pos++]) {
            '"' -> '"'
            '\\' -> '\\'
            '/' -> '/'
            'b' -> '\b'
            'f' -> '\u000C'
            'n' -> '\n'
            'r' -> '\r'
            't' -> '\t'
            'u' -> {
                if (pos + 4 > text.length) fail("JSON \\u 转义需要 4 位十六进制")
                var code = 0
                repeat(4) {
                    val h = text[pos++]
                    val digit = when (h) {
                        in '0'..'9' -> h - '0'
                        in 'a'..'f' -> h - 'a' + 10
                        in 'A'..'F' -> h - 'A' + 10
                        else -> fail("JSON \\u 转义出现非法十六进制字符 '$h'")
                    }
                    code = code * 16 + digit
                }
                code.toChar()
            }
            else -> fail("JSON 非法转义字符 '\\$e'")
        }
    }

    private fun parseNumber(): JsonNumber {
        val start = pos
        if (peek() == '-') pos++
        if (pos >= text.length || text[pos] !in '0'..'9') fail("JSON 数字格式错误")
        while (pos < text.length && text[pos] in '0'..'9') pos++
        var isDouble = false
        if (pos < text.length && text[pos] == '.') {
            isDouble = true
            pos++
            if (pos >= text.length || text[pos] !in '0'..'9') fail("JSON 数字小数部分缺失")
            while (pos < text.length && text[pos] in '0'..'9') pos++
        }
        if (pos < text.length && (text[pos] == 'e' || text[pos] == 'E')) {
            isDouble = true
            pos++
            if (pos < text.length && (text[pos] == '+' || text[pos] == '-')) pos++
            if (pos >= text.length || text[pos] !in '0'..'9') fail("JSON 数字指数部分缺失")
            while (pos < text.length && text[pos] in '0'..'9') pos++
        }
        val raw = text.substring(start, pos)
        val longValue = if (isDouble) raw.toDouble().toLong() else raw.toLong()
        return JsonNumber(isDouble, longValue)
    }

    private fun parseLiteral(literal: String, value: JsonValue): JsonValue {
        if (!text.startsWith(literal, pos)) fail("JSON 非法字面量")
        pos += literal.length
        return value
    }

    private fun skipWhitespace() {
        while (pos < text.length) {
            when (text[pos]) {
                ' ', '\t', '\n', '\r' -> pos++
                else -> return
            }
        }
    }

    private fun peek(): Char {
        if (pos >= text.length) fail("意外到达输入末尾")
        return text[pos]
    }

    private fun expect(c: Char) {
        if (pos >= text.length || text[pos] != c) fail("期望 '$c'")
        pos++
    }

    private fun fail(reason: String): Nothing {
        val line = text.substring(0, pos.coerceAtMost(text.length)).count { it == '\n' } + 1
        throw SessionLogParseException("JSON 解析失败（$reason）：行 $line，字符偏移 $pos")
    }
}
