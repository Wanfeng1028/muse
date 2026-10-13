package com.interlude

import com.interlude.dsl.Parser
import com.interlude.lint.Validator
import java.io.File

/** 冒烟：解析示例剧本并打印校验问题。 */
fun main() {
    val src = File("src/main/resources/scripts/sample.interlude").readText()
    val story = Parser(src).parse()
    println("场景数: ${story.scenes.size}，入口: ${story.entry?.id}")
    val issues = Validator.validate(story)
    println("问题数: ${issues.size}")
    issues.forEach { println("[${it.severity}] ${it.code} ${it.sceneId}:${it.line} ${it.message}") }
}
