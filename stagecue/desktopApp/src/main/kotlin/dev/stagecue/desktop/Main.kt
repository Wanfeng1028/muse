package dev.stagecue.desktop

import androidx.compose.runtime.remember
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.WindowPosition
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import dev.stagecue.desktop.theme.StageCueTheme
import dev.stagecue.desktop.ui.DirectorScreen

fun main() = application {
    val windowState = rememberWindowState(
        size = DpSize(1280.dp, 800.dp),
        position = WindowPosition.Aligned(androidx.compose.ui.Alignment.Center)
    )
    Window(
        onCloseRequest = ::exitApplication,
        title = "舞监台 StageCue",
        state = windowState
    ) {
        StageCueTheme {
            DirectorScreen()
        }
    }
}
