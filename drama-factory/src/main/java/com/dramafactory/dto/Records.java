package com.dramafactory.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.time.LocalDateTime;
import java.util.List;

import com.dramafactory.model.ProjectStatus;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.CharacterRole;
import com.dramafactory.model.ShotSize;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.model.FinalCutStatus;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.RunStatus;

public final class Records {

    private Records() {
    }

    public static record ProjectRequest(
            @NotBlank String title,
            String genre,
            String synopsis,
            ProjectStatus status,
            Integer targetEpisodes
    ) {
    }

    public static record ProjectResponse(
            Long id,
            String title,
            String genre,
            String synopsis,
            ProjectStatus status,
            Integer targetEpisodes,
            long episodeCount,
            long characterCount,
            LocalDateTime createdAt,
            LocalDateTime updatedAt,
            String ownerId
    ) {
    }

    public static record EpisodeRequest(
            @NotNull Integer episodeNo,
            String title,
            String outline,
            EpisodeStatus status,
            Integer durationSec
    ) {
    }

    public static record EpisodeResponse(
            Long id,
            Long projectId,
            Integer episodeNo,
            String title,
            String outline,
            EpisodeStatus status,
            Integer durationSec,
            long sceneCount,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }

    public static record CharacterRequest(
            @NotBlank String name,
            CharacterRole role,
            String description,
            String traits
    ) {
    }

    public static record CharacterResponse(
            Long id,
            Long projectId,
            String name,
            CharacterRole role,
            String description,
            String traits,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }

    public static record SceneRequest(
            @NotNull Integer sceneNo,
            String location,
            String timeOfDay,
            String description,
            String dialogue,
            String prompt
    ) {
    }

    public static record SceneResponse(
            Long id,
            Long episodeId,
            Integer sceneNo,
            String location,
            String timeOfDay,
            String description,
            String dialogue,
            String prompt,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }

    public static record StatsResponse(
            long projects,
            long episodes,
            long characters,
            long scenes
    ) {
    }

    /**
     * 剧本生成响应（v2.3）。
     *
     * @param episodeId 剧集 ID
     * @param sceneCount 场景数
     * @param scriptText 完整剧本文本
     * @param source 生成来源：{@code ai}（大模型生成）、{@code template}（模板生成）、
     *               {@code template-fallback}（AI 失败降级为模板生成）
     * @param model 使用的大模型名，模板生成时为 null
     * @param latencyMs 生成耗时（毫秒）
     * @param promptTokens 输入 token 数（AI 生成时为真实值，否则 0）
     * @param completionTokens 输出 token 数（AI 生成时为真实值，否则 0）
     */
    public static record GenerateScriptResponse(
            Long episodeId,
            int sceneCount,
            String scriptText,
            String source,
            String model,
            long latencyMs,
            long promptTokens,
            long completionTokens) {
    }

    public static record ErrorResponse(
            int status,
            String error,
            String message,
            LocalDateTime timestamp,
            String requestId
    ) {
    }

    public static record ShotRequest(
            @NotNull Integer shotNo,
            ShotSize shotSize,
            CameraMove cameraMove,
            String description,
            Integer durationSeconds,
            String dialogue,
            String videoPrompt
    ) {
    }

    /**
     * 从剧本原文拆分分镜的请求体。
     */
    public static record ScriptSplitRequest(
            @NotBlank String scriptText
    ) {
    }

    /**
     * 成片质检请求体：verdict 只能是 APPROVED（通过）或 REJECTED（打回）。
     */
    public static record QcRequest(
            @NotBlank String verdict,
            String note
    ) {
    }

    /**
     * AI 对话的一条历史消息。
     */
    public static record ChatMessage(
            String role,
            String content
    ) {
    }

    /**
     * AI 对话请求体：message 为本轮用户输入，history 为此前多轮（role/content），
     * episodeId 可选，用于把对话锚定到某个剧集。
     */
    public static record ChatRequest(
            @NotBlank String message,
            Long episodeId,
            List<ChatMessage> history
    ) {
    }

    /**
     * AI 对话响应体。
     */
    public static record ChatResponse(
            String reply,
            String model
    ) {
    }

    /**
     * 对话确认后批量落库的分镜项：景别/运镜用中文标签，由后端映射为枚举。
     */
    public static record ShotBatchItem(
            @NotNull Integer shotNo,
            String shotSize,
            String cameraMove,
            String description,
            Integer durationSeconds,
            String dialogue,
            String videoPrompt
    ) {
    }

    /**
     * 批量落库分镜的请求体（替换该剧集全部旧分镜）。
     */
    public static record ShotBatchRequest(
            @NotNull List<ShotBatchItem> shots
    ) {
    }

    public static record ShotResponse(
            Long id,
            Long episodeId,
            Integer shotNo,
            ShotSize shotSize,
            String shotSizeLabel,
            CameraMove cameraMove,
            String cameraMoveLabel,
            String description,
            Integer durationSeconds,
            String dialogue,
            String videoPrompt,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }

    public static record ReorderRequest(
            List<Long> shotIds
    ) {
    }

    public static record VideoTaskResponse(
            Long id,
            Long shotId,
            String provider,
            String providerTaskId,
            VideoTaskStatus status,
            String statusLabel,
            Integer attempts,
            String videoUrl,
            Boolean hasLocalFile,
            String errorMessage,
            LocalDateTime nextRetryAt,
            LocalDateTime createdAt,
            LocalDateTime updatedAt,
            String fallbackReason
    ) {
    }

    /**
     * 提交结果封装：task 为最终返回给客户端的任务视图；created 表示本次调用是否真正新建了任务。
     * 幂等命中已存在 PENDING/PROCESSING 任务时 created=false；新建时 created=true。
     * Controller 可据此选择 REST 状态码（新建 201，命中 200）。
     */
    public static record SubmitOutcome(VideoTaskResponse task, boolean created) {
    }

    public static record FinalCutResponse(
            Long id,
            Long episodeId,
            String title,
            String filePath,
            String fileName,
            FinalCutStatus status,
            String statusLabel,
            Double durationSeconds,
            String errorMessage,
            String qcStatus,
            String qcNote,
            LocalDateTime qcAt,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }

    public static record PipelineEpisodeView(
            Long episodeId,
            Integer episodeNo,
            String title,
            String status,
            long shotCount,
            long pendingTasks,
            long processingTasks,
            long doneTasks,
            long failedTasks,
            String finalCutStatus
    ) {
    }

    public static record PipelineProjectView(
            Long projectId,
            String title,
            List<PipelineEpisodeView> episodes
    ) {
    }

    /**
     * 生产统计：分镜完成率 = 拥有 DONE 视频任务的分镜数 / 分镜总数；
     * 任务成功率 = DONE 任务数 / (DONE + FAILED) 任务数；
     * 累计渲染时长 = 所有 DONE 任务对应分镜的 durationSeconds 之和。
     */
    public static record ProductionStatsResponse(
            Long projectId,
            long shotCount,
            long shotsCompleted,
            double shotCompletionRate,
            long tasksDone,
            long tasksFailed,
            double taskSuccessRate,
            long totalRenderSeconds
    ) {
    }

/**
     * 计划中的单集信息。
     *
     * @param episodeNo 集号
     * @param title     标题
     * @param outline   大纲
     */
    public record PlanEpisode(Integer episodeNo, String title, String outline) {
    }

    /**
     * 计划预览结果。
     *
     * @param goal       目标描述
     * @param episodes   剧集计划列表
     * @param fallback   是否由回退逻辑生成
     */
    public record PlanPreview(String goal, List<PlanEpisode> episodes, boolean fallback) {
    }

    /**
     * Run 响应。
     *
     * @param id             Run 主键
     * @param goal           目标描述
     * @param status         状态枚举
     * @param statusLabel    状态中文标签
     * @param projectId      关联项目主键
     * @param totalTokens    累计 Token 数
     * @param totalCostCents 累计费用（分）
     * @param createdAt      创建时间
     * @param updatedAt      更新时间
     */
    public record RunResponse(Long id, String goal, RunStatus status, String statusLabel, Long projectId,
                              Long totalTokens, Long totalCostCents,
                              LocalDateTime createdAt, LocalDateTime updatedAt) {
    }

    /**
     * 步骤响应。
     *
     * @param id            步骤主键
     * @param seqNo         序号
     * @param agentType     智能体类型
     * @param agentLabel    智能体中文标签
     * @param name          步骤名称
     * @param status        状态
     * @param statusLabel   状态中文标签
     * @param episodeId     关联剧集主键
     * @param inputSummary  输入摘要
     * @param outputSummary 输出摘要
     * @param toolCallsJson 工具调用 JSON
     * @param tokensUsed    消耗 Token 数
     * @param costCents     消耗费用（分）
     * @param costEstimated 费用是否为估算值
     * @param latencyMs     耗时（毫秒）
     * @param errorMessage  错误信息
     * @param startedAt     开始时间
     * @param endedAt       结束时间
     */
    public record AgentStepResponse(Long id, Integer seqNo, AgentType agentType, String agentLabel, String name,
                                    AgentStepStatus status, String statusLabel, Long episodeId,
                                    String inputSummary, String outputSummary, String toolCallsJson,
                                    Long tokensUsed, Long costCents, Boolean costEstimated, Long latencyMs,
                                    String errorMessage, LocalDateTime startedAt, LocalDateTime endedAt) {
    }

    /**
     * Run 详情响应。
     *
     * @param run       Run 响应
     * @param steps     步骤响应列表
     * @param projectId 关联项目主键
     */
    public record RunDetailResponse(RunResponse run, List<AgentStepResponse> steps, Long projectId) {
    }

    /**
     * Run 统计响应。
     *
     * @param totalRuns     Run 总数
     * @param succeeded     成功数
     * @param failed        失败数
     * @param successRate   成功率
     * @param avgDurationMs 平均耗时（毫秒）
     */
    public record RunStatsResponse(long totalRuns, long succeeded, long failed, double successRate, long avgDurationMs) {
    }

    /**
     * 日志读取响应。
     *
     * @param content    日志内容
     * @param nextOffset 下次读取偏移量
     * @param eof        是否已到末尾
     */
    public record LogReadResponse(String content, long nextOffset, boolean eof) {
    }

    /**
     * 重跑请求。
     *
     * @param goal 新的目标描述（可为空表示沿用原目标）
     */
    public record RerunRequest(String goal) {
    }

    /** Agent 信息。 */
    public record AgentInfo(String type, String label, String templateName, LocalDateTime templateUpdatedAt,
                            String model, String fallback) {
    }
    /** 剧集产物。 */
    public record EpisodeArtifacts(Long episodeId, Integer episodeNo, String title, String scriptText,
                                   List<ShotArtifact> shots, List<VideoArtifact> videos,
                                   List<FinalCutArtifact> finalCuts) {
    }
    /** 分镜产物。 */
    public record ShotArtifact(Long id, Integer shotNo, String shotSize, String cameraMove,
                               String description, Integer durationSeconds) {
    }
    /** 视频任务产物。 */
    public record VideoArtifact(Long taskId, Long shotId, String provider, String modelUsed,
                                String status, String statusLabel, String url, Long costCents) {
    }
    /** 成片产物。 */
    public record FinalCutArtifact(Long id, String filePath, String url, String status,
                                   String qcStatus, String qcNote, Double durationSeconds) {
    }
    /** 运行产物响应。 */
    public record RunArtifactsResponse(Long runId, List<EpisodeArtifacts> episodes) {
    }
    /** 视频通道信息。 */
    public record ChannelInfo(String current, List<String> available, String note) {
    }
}
