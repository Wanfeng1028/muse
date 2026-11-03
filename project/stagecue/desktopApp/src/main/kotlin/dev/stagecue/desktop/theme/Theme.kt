package dev.stagecue.desktop.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// 深炭黑底 / 追光金 / 幕布红 / 粉笔白 / 暗金边框
object StageColors {
    val Charcoal = Color(0xFF17130F)
    val Spotlight = Color(0xFFE0A83E)
    val Curtain = Color(0xFF9E2B25)
    val Chalk = Color(0xFFF2EDE3)
    val DimGold = Color(0xFF3A2F22)
    val Panel = Color(0xFF1E1813)
    val PanelAlt = Color(0xFF231C16)
    val LightBadge = Color(0xFF6E7B8B)
    val Connected = Color(0xFF4F9E5B)
    val Disconnected = Color(0xFFB0392F)
    val SubtleText = Color(0xFF9A8F7F)
}

private val StageColorScheme = darkColorScheme(
    primary = StageColors.Spotlight,
    onPrimary = StageColors.Charcoal,
    secondary = StageColors.Curtain,
    onSecondary = StageColors.Chalk,
    background = StageColors.Charcoal,
    onBackground = StageColors.Chalk,
    surface = StageColors.Panel,
    onSurface = StageColors.Chalk,
    surfaceVariant = StageColors.PanelAlt,
    onSurfaceVariant = StageColors.SubtleText,
    outline = StageColors.DimGold,
    error = StageColors.Curtain,
    onError = StageColors.Chalk
)

private val StageTypography = Typography(
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 14.sp,
        color = StageColors.Chalk
    ),
    bodySmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 12.sp,
        color = StageColors.SubtleText
    ),
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 20.sp,
        fontWeight = FontWeight.Bold,
        color = StageColors.Chalk
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 16.sp,
        fontWeight = FontWeight.SemiBold,
        color = StageColors.Chalk
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 11.sp,
        color = StageColors.SubtleText
    )
)

// 时间码样式：等宽 28sp
val TimecodeStyle = TextStyle(
    fontFamily = FontFamily.Monospace,
    fontSize = 28.sp,
    fontWeight = FontWeight.Medium,
    color = StageColors.Spotlight
)

// 通用等宽样式
val MonoStyle = TextStyle(
    fontFamily = FontFamily.Monospace,
    fontSize = 14.sp,
    color = StageColors.Chalk
)

@Composable
fun StageCueTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = StageColorScheme,
        typography = StageTypography,
        content = content
    )
}
