package dev.stagecue.desktop.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.stagecue.desktop.theme.StageColors

@Composable
fun EventLogPanel(
    modifier: Modifier = Modifier,
    lines: List<String>
) {
    Column(modifier = modifier.background(StageColors.Panel)) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .height(36.dp)
                .background(StageColors.PanelAlt)
                .padding(horizontal = 12.dp),
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                text = "场记 log",
                color = StageColors.SubtleText,
                fontSize = 12.sp,
                fontFamily = FontFamily.Monospace
            )
        }
        val listState = rememberLazyListState()
        LaunchedEffect(lines.firstOrNull()) {
            if (lines.isNotEmpty()) listState.animateScrollToItem(0)
        }
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            state = listState,
            reverseLayout = false
        ) {
            items(lines) { line ->
                Text(
                    text = line,
                    color = StageColors.Chalk,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 12.sp,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 4.dp)
                )
            }
        }
    }
}
