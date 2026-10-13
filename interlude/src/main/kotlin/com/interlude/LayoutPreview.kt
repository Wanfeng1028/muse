package com.interlude

import com.interlude.dsl.Parser
import com.interlude.ui.GraphLayout
import java.awt.BasicStroke
import java.awt.Color
import java.awt.Font
import java.awt.RenderingHints
import java.awt.image.BufferedImage
import java.io.File
import javax.imageio.ImageIO

/**
 * 布局算法可视化验证（非 App 界面截图）：
 * 用 GraphLayout 的真实输出绘制分支图，肉眼检查分层/节点重叠。
 */
fun main() {
    val src = File("src/main/resources/scripts/sample.interlude").readText()
    val story = Parser(src).parse()
    val (pos, edges) = GraphLayout.layout(story)

    val ink = Color(0x1B1712)
    val paper = Color(0xE8DCC0)
    val vermilion = Color(0xC8402A)
    val amber = Color(0xD9A441)
    val edgeGray = Color(0x6B6154)

    val img = BufferedImage(1400, 900, BufferedImage.TYPE_INT_RGB)
    val g = img.createGraphics()
    g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
    g.color = ink
    g.fillRect(0, 0, 1400, 900)
    g.font = Font("SansSerif", Font.BOLD, 14)

    val cardW = 200f
    val cardH = 90f
    for (e in edges) {
        val from = pos[e.from] ?: continue
        val to = pos[e.to] ?: continue
        g.color = edgeGray
        g.stroke = BasicStroke(2f)
        val x1 = (from.x + cardW).toInt()
        val y1 = (from.y + cardH / 2).toInt()
        val x2 = to.x.toInt()
        val y2 = (to.y + cardH / 2).toInt()
        g.drawLine(x1, y1, x2, y2)
    }
    for (scene in story.scenes) {
        val p = pos[scene.id] ?: continue
        val x = p.x.toInt()
        val y = p.y.toInt()
        g.color = paper
        g.fillRoundRect(x, y, cardW.toInt(), cardH.toInt(), 16, 16)
        g.color = ink
        g.drawString(scene.id, x + 12, y + 24)
    }
    g.dispose()
    File("build/layout-preview.png").apply { parentFile.mkdirs() }
    ImageIO.write(img, "png", File("build/layout-preview.png"))
    println("written build/layout-preview.png, scenes=${story.scenes.size}, edges=${edges.size}")
}
