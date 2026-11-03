package com.dramafactory.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Lob;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * Harness 中的单个 Agent 步骤，隶属于某个 {@link Run}。
 */
@Entity
@Table(name = "agent_steps")
public class AgentStep {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 所属运行 */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "run_id", nullable = false)
    private Run run;

    /** 步骤序号 */
    @Column(name = "seq_no", nullable = false)
    private Integer seqNo;

    /** Agent 类型 */
    @Enumerated(EnumType.STRING)
    @Column(name = "agent_type", length = 32)
    private AgentType agentType;

    /** 步骤名称 */
    @Column(name = "name", length = 200)
    private String name;

    /** 步骤状态 */
    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 32)
    private AgentStepStatus status;

    /** 关联剧集 ID，可空 */
    @Column(name = "episode_id")
    private Long episodeId;

    /** 本步骤使用的 Skill ID，可空 */
    @Column(name = "skill_id")
    private Long skillId;

    /** 输入摘要 */
    @Lob
    @Column(name = "input_summary")
    private String inputSummary;

    /** 输出摘要 */
    @Lob
    @Column(name = "output_summary")
    private String outputSummary;

    /** 工具调用记录（JSON 数组文本） */
    @Lob
    @Column(name = "tool_calls_json")
    private String toolCallsJson;

    /** 消耗 token 总数，可空；新代码优先用 prompt/completion 拆分字段 */
    @Column(name = "tokens_used")
    private Long tokensUsed;

    /** prompt token 数，可空 */
    @Column(name = "prompt_tokens")
    private Long promptTokens;

    /** completion token 数，可空 */
    @Column(name = "completion_tokens")
    private Long completionTokens;

    /** 缓存命中 token 数，可空 */
    @Column(name = "cached_tokens")
    private Long cachedTokens;

    /** 消耗（分），可空 */
    @Column(name = "cost_cents")
    private Long costCents;

    /** 是否为估算成本 */
    @Column(name = "cost_estimated")
    private Boolean costEstimated = false;

    /** 延迟毫秒，可空 */
    @Column(name = "latency_ms")
    private Long latencyMs;

    /** 错误信息 */
    @Column(name = "error_message", length = 2000)
    private String errorMessage;

    @Column(name = "started_at")
    private LocalDateTime startedAt;

    @Column(name = "ended_at")
    private LocalDateTime endedAt;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @PrePersist
    public void prePersist() {
        LocalDateTime now = LocalDateTime.now();
        this.createdAt = now;
        this.updatedAt = now;
    }

    @PreUpdate
    public void preUpdate() {
        this.updatedAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public Run getRun() {
        return run;
    }

    public void setRun(Run run) {
        this.run = run;
    }

    public Integer getSeqNo() {
        return seqNo;
    }

    public void setSeqNo(Integer seqNo) {
        this.seqNo = seqNo;
    }

    public AgentType getAgentType() {
        return agentType;
    }

    public void setAgentType(AgentType agentType) {
        this.agentType = agentType;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public AgentStepStatus getStatus() {
        return status;
    }

    public void setStatus(AgentStepStatus status) {
        this.status = status;
    }

    public Long getEpisodeId() {
        return episodeId;
    }

    public void setEpisodeId(Long episodeId) {
        this.episodeId = episodeId;
    }

    /**
     * 获取本步骤使用的 Skill ID。
     *
     * @return Skill ID，可空
     */
    public Long getSkillId() {
        return skillId;
    }

    /**
     * 设置本步骤使用的 Skill ID。
     *
     * @param skillId Skill ID，可空
     */
    public void setSkillId(Long skillId) {
        this.skillId = skillId;
    }

    public String getInputSummary() {
        return inputSummary;
    }

    public void setInputSummary(String inputSummary) {
        this.inputSummary = inputSummary;
    }

    public String getOutputSummary() {
        return outputSummary;
    }

    public void setOutputSummary(String outputSummary) {
        this.outputSummary = outputSummary;
    }

    public String getToolCallsJson() {
        return toolCallsJson;
    }

    public void setToolCallsJson(String toolCallsJson) {
        this.toolCallsJson = toolCallsJson;
    }

    public Long getTokensUsed() {
        return tokensUsed;
    }

    public void setTokensUsed(Long tokensUsed) {
        this.tokensUsed = tokensUsed;
    }

    public Long getPromptTokens() {
        return promptTokens;
    }

    public void setPromptTokens(Long promptTokens) {
        this.promptTokens = promptTokens;
    }

    public Long getCompletionTokens() {
        return completionTokens;
    }

    public void setCompletionTokens(Long completionTokens) {
        this.completionTokens = completionTokens;
    }

    public Long getCachedTokens() {
        return cachedTokens;
    }

    public void setCachedTokens(Long cachedTokens) {
        this.cachedTokens = cachedTokens;
    }

    public Long getCostCents() {
        return costCents;
    }

    public void setCostCents(Long costCents) {
        this.costCents = costCents;
    }

    public Boolean getCostEstimated() {
        return costEstimated;
    }

    public void setCostEstimated(Boolean costEstimated) {
        this.costEstimated = costEstimated;
    }

    public Long getLatencyMs() {
        return latencyMs;
    }

    public void setLatencyMs(Long latencyMs) {
        this.latencyMs = latencyMs;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }

    public LocalDateTime getStartedAt() {
        return startedAt;
    }

    public void setStartedAt(LocalDateTime startedAt) {
        this.startedAt = startedAt;
    }

    public LocalDateTime getEndedAt() {
        return endedAt;
    }

    public void setEndedAt(LocalDateTime endedAt) {
        this.endedAt = endedAt;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(LocalDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }
}
