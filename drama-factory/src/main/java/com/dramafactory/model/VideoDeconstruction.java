package com.dramafactory.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import java.time.LocalDateTime;

/**
 * 视频拆解任务：对一条源视频做场景切分、关键帧抽取与节奏/结构分析，产出结构化拆解。
 */
@Entity
@Table(name = "video_deconstructions")
public class VideoDeconstruction {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 所属项目 id */
    @Column(name = "project_id", nullable = false)
    private Long projectId;

    /** 来源素材 id（上传输入时为空） */
    @Column(name = "asset_id")
    private Long assetId;

    /** 源视频显示名 */
    @Column(name = "source_name", length = 500)
    private String sourceName;

    /** 源视频在存储根下的相对路径 */
    @Column(name = "source_path", length = 1000, nullable = false)
    private String sourcePath;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", length = 16, nullable = false)
    private DeconstructionStatus status;

    @Column(name = "error_message", length = 2000)
    private String errorMessage;

    /** 时长秒（ffprobe 实测） */
    @Column(name = "duration_sec")
    private Double durationSec;

    /** 分辨率宽（实测） */
    private Integer width;

    /** 分辨率高（实测） */
    private Integer height;

    /** 帧率（实测） */
    private Double fps;

    /** 码率 bps（实测） */
    @Column(name = "bit_rate")
    private Long bitRate;

    /** 切分镜数 */
    @Column(name = "shot_count")
    private Integer shotCount;

    @Column(name = "avg_shot_duration_sec")
    private Double avgShotDurationSec;

    /** 每分钟切镜数=(镜数-1)/时长分钟 */
    @Column(name = "cuts_per_minute")
    private Double cutsPerMinute;

    /** 节奏分类（规则推断：快节奏/中节奏/慢节奏） */
    @Column(name = "rhythm_class", length = 32)
    private String rhythmClass;

    /** 钩子段结束秒（规则推断） */
    @Column(name = "hook_end_sec")
    private Double hookEndSec;

    /** 结构化拆解结果 JSON（结构段/公式/剧本模板） */
    @Column(name = "result_json", columnDefinition = "CLOB")
    private String resultJson;

    /** Markdown 拆解报告全文 */
    @Column(name = "report_md", columnDefinition = "CLOB")
    private String reportMd;

    @Column(name = "transcript_status", length = 16)
    private String transcriptStatus;

    @Column(name = "transcript_track_info", length = 200)
    private String transcriptTrackInfo;

    @Column(name = "transcript_json", columnDefinition = "CLOB")
    private String transcriptJson;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        this.updatedAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public Long getProjectId() {
        return projectId;
    }

    public void setProjectId(Long projectId) {
        this.projectId = projectId;
    }

    public Long getAssetId() {
        return assetId;
    }

    public void setAssetId(Long assetId) {
        this.assetId = assetId;
    }

    public String getSourceName() {
        return sourceName;
    }

    public void setSourceName(String sourceName) {
        this.sourceName = sourceName;
    }

    public String getSourcePath() {
        return sourcePath;
    }

    public void setSourcePath(String sourcePath) {
        this.sourcePath = sourcePath;
    }

    public DeconstructionStatus getStatus() {
        return status;
    }

    public void setStatus(DeconstructionStatus status) {
        this.status = status;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }

    public Double getDurationSec() {
        return durationSec;
    }

    public void setDurationSec(Double durationSec) {
        this.durationSec = durationSec;
    }

    public Integer getWidth() {
        return width;
    }

    public void setWidth(Integer width) {
        this.width = width;
    }

    public Integer getHeight() {
        return height;
    }

    public void setHeight(Integer height) {
        this.height = height;
    }

    public Double getFps() {
        return fps;
    }

    public void setFps(Double fps) {
        this.fps = fps;
    }

    public Long getBitRate() {
        return bitRate;
    }

    public void setBitRate(Long bitRate) {
        this.bitRate = bitRate;
    }

    public Integer getShotCount() {
        return shotCount;
    }

    public void setShotCount(Integer shotCount) {
        this.shotCount = shotCount;
    }

    public Double getAvgShotDurationSec() {
        return avgShotDurationSec;
    }

    public void setAvgShotDurationSec(Double avgShotDurationSec) {
        this.avgShotDurationSec = avgShotDurationSec;
    }

    public Double getCutsPerMinute() {
        return cutsPerMinute;
    }

    public void setCutsPerMinute(Double cutsPerMinute) {
        this.cutsPerMinute = cutsPerMinute;
    }

    public String getRhythmClass() {
        return rhythmClass;
    }

    public void setRhythmClass(String rhythmClass) {
        this.rhythmClass = rhythmClass;
    }

    public Double getHookEndSec() {
        return hookEndSec;
    }

    public void setHookEndSec(Double hookEndSec) {
        this.hookEndSec = hookEndSec;
    }

    public String getResultJson() {
        return resultJson;
    }

    public void setResultJson(String resultJson) {
        this.resultJson = resultJson;
    }

    public String getReportMd() {
        return reportMd;
    }

    public void setReportMd(String reportMd) {
        this.reportMd = reportMd;
    }

    public String getTranscriptStatus() {
        return transcriptStatus;
    }

    public void setTranscriptStatus(String transcriptStatus) {
        this.transcriptStatus = transcriptStatus;
    }

    public String getTranscriptTrackInfo() {
        return transcriptTrackInfo;
    }

    public void setTranscriptTrackInfo(String transcriptTrackInfo) {
        this.transcriptTrackInfo = transcriptTrackInfo;
    }

    public String getTranscriptJson() {
        return transcriptJson;
    }

    public void setTranscriptJson(String transcriptJson) {
        this.transcriptJson = transcriptJson;
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
