
package com.interlude

import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import com.interlude.ui.App

fun main() = application {
    Window(
        onCloseRequest = ::exitApplication,
        title = "幕间 Interlude"
    ) {
        App()
    }
}
