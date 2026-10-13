package dev.stagecue.desktop.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.stagecue.desktop.theme.StageColors

@Composable
fun TransportBar(
    rehearsal: Boolean,
    onToggleRehearsal: () -> Unit,
    onArm: () -> Unit,
    onTrigger: () -> Unit,
    firedCount: Int
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(88.dp)
            .background(StageColors.Panel)
            .padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        BigButton(label = "预备", color = StageColors.Charcoal, border = StageColors.Spotlight, textColor = StageColors.Spotlight, onClick = onArm)
        Spacer(Modifier.width(12.dp))
        BigButton(label = "触发", color = StageColors.Curtain, border = StageColors.Curtain, textColor = StageColors.Chalk, onClick = onTrigger)
        Spacer(Modifier.width(24.dp))
        RehearsalSwitch(rehearsal = rehearsal, onToggle = onToggleRehearsal)
        Spacer(Modifier.width(24.dp))
        Text(
            text = "fallback：断连时本地无网络，仅播音频，其他 cue 请手动上。",
            color = StageColors.SubtleText,
            fontSize = 12.sp,
            modifier = Modifier.weight(1f)
        )
        Spacer(Modifier.width(16.dp))
        Text(
            text = "已触发 $firedCount",
            color = StageColors.Spotlight,
            fontFamily = FontFamily.Monospace,
            fontSize = 16.sp,
            fontWeight = FontWeight.Medium
        )
    }
}

@Composable
private fun BigButton(
    label: String,
    color: androidx.compose.ui.graphics.Color,
    border: androidx.compose.ui.graphics.Color,
    textColor: androidx.compose.ui.graphics.Color,
    onClick: () -> Unit
) {
    Box(
        modifier = Modifier
            .width(140.dp)
            .height(56.dp)
            .background(color)
            .border(2.dp, border)
            .clickable { onClick() },
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = label,
            color = textColor,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold
        )
    }
}

@Composable
private fun RehearsalSwitch(rehearsal: Boolean, onToggle: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .width(56.dp)
                .height(28.dp)
                .background(if (rehearsal) StageColors.Spotlight else StageColors.Charcoal)
                .border(2.dp, if (rehearsal) StageColors.Spotlight else StageColors.DimGold)
                .clickable { onToggle() },
            contentAlignment = if (rehearsal) Alignment.CenterEnd else Alignment.CenterStart
        ) {
            Box(
                modifier = Modifier
                    .width(24.dp)
                    .height(24.dp)
                    .background(if (rehearsal) StageColors.Charcoal else StageColors.DimGold)
            )
        }
        Spacer(Modifier.width(10.dp))
        Text(
            text = if (rehearsal) "排练模式 · 开" else "排练模式 · 关",
            color = if (rehearsal) StageColors.Spotlight else StageColors.SubtleText,
            fontSize = 14.sp,
            fontWeight = if (rehearsal) FontWeight.SemiBold else FontWeight.Normal
        )
    }
}
