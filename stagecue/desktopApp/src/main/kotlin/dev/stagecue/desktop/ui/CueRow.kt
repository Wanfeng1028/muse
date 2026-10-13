package dev.stagecue.desktop.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.stagecue.desktop.theme.StageColors
import dev.stagecue.shared.model.Cue
import dev.stagecue.shared.model.CueState
import dev.stagecue.shared.model.CueType

@Composable
fun CueListPanel(
    modifier: Modifier = Modifier,
    cues: List<Cue>,
    states: Map<String, CueState>,
    currentCueId: String?,
    selectedCueId: String?,
    onSelect: (String) -> Unit,
    onArm: (String) -> Unit
) {
    Column(modifier = modifier.background(StageColors.Charcoal)) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(36.dp)
                .background(StageColors.Panel)
                .padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "CUE 时间轴",
                color = StageColors.SubtleText,
                fontSize = 12.sp,
                fontFamily = FontFamily.Monospace
            )
            Spacer(Modifier.weight(1f))
            Text(
                text = "共 ${cues.size} 条",
                color = StageColors.SubtleText,
                fontSize = 12.sp,
                fontFamily = FontFamily.Monospace
            )
        }
        if (cues.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxSize().padding(24.dp),
                contentAlignment = Alignment.TopStart
            ) {
                Text(
                    text = "暂无 cue。等服务器推过来。",
                    color = StageColors.SubtleText,
                    fontSize = 14.sp
                )
            }
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize()) {
                items(cues, key = { it.id }) { cue ->
                    CueRow(
                        cue = cue,
                        state = states[cue.id],
                        isCurrent = cue.id == currentCueId,
                        isSelected = cue.id == selectedCueId,
                        onSelect = { onSelect(cue.id) },
                        onDoubleClick = { onArm(cue.id) }
                    )
                }
            }
        }
    }
}

@Composable
fun CueRow(
    cue: Cue,
    state: CueState?,
    isCurrent: Boolean,
    isSelected: Boolean,
    onSelect: () -> Unit,
    onDoubleClick: () -> Unit
) {
    val bg = when {
        isCurrent -> StageColors.Spotlight
        isSelected -> StageColors.PanelAlt
        else -> StageColors.Charcoal
    }
    val fg = if (isCurrent) StageColors.Charcoal else StageColors.Chalk

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(52.dp)
            .background(bg)
            .then(
                if (isSelected && !isCurrent)
                    Modifier.border(1.dp, StageColors.Spotlight)
                else Modifier
            )
            .clickable { onSelect() }
            .padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = cue.order.toString().padStart(3, '0'),
            color = if (isCurrent) StageColors.Charcoal else StageColors.Spotlight,
            fontFamily = FontFamily.Monospace,
            fontSize = 15.sp,
            fontWeight = FontWeight.Medium,
            modifier = Modifier.width(56.dp)
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = cue.name,
            color = fg,
            fontSize = 15.sp,
            fontWeight = if (isCurrent) FontWeight.SemiBold else FontWeight.Normal,
            modifier = Modifier.weight(1f)
        )
        TypeBadge(type = cue.type, dim = isCurrent)
        Spacer(Modifier.width(16.dp))
        Text(
            text = formatDuration(cue.durationMs),
            color = if (isCurrent) StageColors.Charcoal else StageColors.SubtleText,
            fontFamily = FontFamily.Monospace,
            fontSize = 13.sp,
            modifier = Modifier.width(72.dp)
        )
        Spacer(Modifier.width(12.dp))
        StateDot(state = state, dim = isCurrent)
    }
}

@Composable
private fun TypeBadge(type: CueType, dim: Boolean) {
    val (label, color) = when (type) {
        CueType.AUDIO -> "AUDIO" to StageColors.Spotlight
        CueType.LIGHT -> "LIGHT" to StageColors.LightBadge
        CueType.SUBTITLE -> "SUBTITLE" to StageColors.Chalk
        CueType.PROMPT -> "PROMPT" to StageColors.Curtain
        else -> type.name to StageColors.SubtleText
    }
    val bg = if (dim) StageColors.Charcoal else color
    val fg = if (dim) color else StageColors.Charcoal
    Box(
        modifier = Modifier
            .height(20.dp)
            .background(bg)
            .border(1.dp, color)
            .padding(horizontal = 8.dp),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = label,
            color = fg,
            fontFamily = FontFamily.Monospace,
            fontSize = 11.sp,
            fontWeight = FontWeight.Medium
        )
    }
}

@Composable
private fun StateDot(state: CueState?, dim: Boolean) {
    val color = when (state) {
        CueState.FIRING -> StageColors.Curtain
        CueState.ARMED -> StageColors.Spotlight
        CueState.IDLE -> StageColors.Chalk
        else -> StageColors.DimGold
    }
    Box(
        modifier = Modifier
            .size(10.dp)
            .background(color)
    )
}

private fun formatDuration(ms: Long): String {
    if (ms <= 0) return "00:00"
    val totalSec = ms / 1000
    val m = totalSec / 60
    val s = totalSec % 60
    return "%02d:%02d".format(m, s)
}
