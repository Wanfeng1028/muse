package com.interlude.replay

import com.interlude.dsl.Story
import com.interlude.dsl.Text

/** 一个抉择点：一次有备选项没选的选择。 */
data class DecisionPoint(
    val sceneId: String,
    val sceneLine: Int, // 剧本中该场景的行号；story 为 null 或场景不存在时为 -1
    val sceneText: String, // 该场景第一段 text 正文；无则 ""
    val chosenLabel: String,
    val chosenTarget: String,
    val alternatives: List<Alternative>,
)

/** 一轮投票：同 round 的 VoteCast + 该轮的 Elimination（可无）。 */
data class VoteRound(val round: Int, val votes: List<VoteCast>, val eliminated: Elimination?)

/** 单个玩家的对局统计，用于 MVP 评选输入。 */
data class PlayerStats(
    val player: String,
    val votesCast: Int, // 投出票数
    val votesReceived: Int, // 被投票数
    val eliminatedRound: Int?, // 出局轮次，未出局为 null
)

data class ReplayReport(
    val sessionId: String,
    val scriptFile: String,
    val startedAt: String,
    val endedAt: String?, // 无 SessionEnd 时为 null
    val timeline: List<SessionEvent>, // 全部事件（含 SessionStart），保持原顺序
    val decisionPoints: List<DecisionPoint>,
    val voteRounds: List<VoteRound>,
    val playerStats: List<PlayerStats>, // 按 votesReceived 降序
    val keyMoments: List<KeyMoment>,
    val outcome: String?,
    val winner: String?,
    val warnings: List<String>, // 如 "事件 events[2] 引用的场景 'xxx' 在剧本中不存在"
)

object ReplayAnalyzer {
    /**
     * 根据可选剧本和对局事件构建复盘报告。
     * story 为 null 时不做场景富化，也不产生场景缺失警告。
     */
    fun buildReport(story: Story?, events: List<SessionEvent>): ReplayReport {
        if (events.isEmpty()) {
            throw IllegalArgumentException("事件列表为空，至少需要一个 SessionStart")
        }
        val first = events[0]
        if (first !is SessionStart) {
            throw IllegalArgumentException("第一个事件必须是 SessionStart")
        }

        val warnings = mutableListOf<String>()

        // 抉择点：有备选项的 ChoiceMade；warnings 按事件时间线顺序产生
        val decisionPoints = mutableListOf<DecisionPoint>()
        events.forEachIndexed { index, event ->
            if (story != null && event is SceneEnter && story.sceneById(event.sceneId) == null) {
                warnings.add(
                    "事件 events[$index] 引用的场景 '${event.sceneId}' 在剧本中不存在"
                )
            }
            if (event is ChoiceMade && event.alternatives.isNotEmpty()) {
                var sceneLine = -1
                var sceneText = ""
                if (story != null) {
                    val scene = story.sceneById(event.sceneId)
                    if (scene == null) {
                        warnings.add(
                            "事件 events[$index] 引用的场景 '${event.sceneId}' 在剧本中不存在"
                        )
                    } else {
                        sceneLine = scene.line
                        val textStmt = scene.statements.firstOrNull { it is Text } as? Text
                        sceneText = textStmt?.value ?: ""
                    }
                }
                decisionPoints.add(
                    DecisionPoint(
                        sceneId = event.sceneId,
                        sceneLine = sceneLine,
                        sceneText = sceneText,
                        chosenLabel = event.label,
                        chosenTarget = event.target,
                        alternatives = event.alternatives,
                    )
                )
            }
        }

        // 投票轮次：按 round 升序分组
        val voteRounds = mutableListOf<VoteRound>()
        val votesByRound = events.filterIsInstance<VoteCast>().groupBy { it.round }
        val eliminationByRound = events.filterIsInstance<Elimination>().groupBy { it.round }
        val sortedRounds = votesByRound.keys.sorted()
        for (round in sortedRounds) {
            val votes = votesByRound.getValue(round)
            val elim = eliminationByRound[round]?.firstOrNull()
            voteRounds.add(VoteRound(round = round, votes = votes, eliminated = elim))
        }

        // 玩家统计
        val players = linkedSetOf<String>()
        events.forEach { event ->
            when (event) {
                is VoteCast -> {
                    players.add(event.voter)
                    players.add(event.target)
                }
                is Elimination -> players.add(event.player)
                else -> {}
            }
        }
        val playerStats = players.map { player ->
            val cast = events.filterIsInstance<VoteCast>().count { it.voter == player }
            val received = events.filterIsInstance<VoteCast>().count { it.target == player }
            val eliminatedRound = events.filterIsInstance<Elimination>()
                .firstOrNull { it.player == player }?.round
            PlayerStats(
                player = player,
                votesCast = cast,
                votesReceived = received,
                eliminatedRound = eliminatedRound,
            )
        }.sortedWith(compareByDescending<PlayerStats> { it.votesReceived }.thenBy { it.player })

        // 关键标注
        val keyMoments = events.filterIsInstance<KeyMoment>()

        // 结局：取最后一个 SessionEnd
        val lastEnd = events.filterIsInstance<SessionEnd>().lastOrNull()

        return ReplayReport(
            sessionId = first.sessionId,
            scriptFile = first.scriptFile,
            startedAt = first.at,
            endedAt = lastEnd?.at,
            timeline = events,
            decisionPoints = decisionPoints,
            voteRounds = voteRounds,
            playerStats = playerStats,
            keyMoments = keyMoments,
            outcome = lastEnd?.outcome,
            winner = lastEnd?.winner,
            warnings = warnings,
        )
    }
}