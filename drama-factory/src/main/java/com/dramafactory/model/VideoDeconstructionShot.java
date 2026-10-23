package com.dramafactory.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import java.time.LocalDateTime;

/**
 * 视频拆解的逐镜结果：一镜一行，含起止时间、关键帧与反推提示词。
 */
@Entity
@Table(name = "video_deconstruction_shots")
public class VideoDeconstructionShot {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "deconstruction_id", nullable = false)
    private Long deconstructionId;

    /** 镜号（从 1 起） */
    @Column(name = "shot_no", nullable = false)
    private Integer shotNo;

    /** 起始秒（实测） */
    @Column(name = "start_sec")
    private Double startSec;

    /** 结束秒（实测） */
    @Column(name = "end_sec")
    private Double endSec;

    /** 时长秒（实测） */
    @Column(name = "duration_sec")
    private Double durationSec;

    /** 关键帧相对路径 */
    @Column(name = "keyframe_path", length = 1000)
    private String keyframePath;

    /** 结构角色（规则推断：钩子/主体/转折/收尾） */
    @Column(name = "segment_role", length = 32)
    private String segmentRole;

    /** 时长类别（规则推断：短切/常规/长镜） */
    @Column(name = "duration_class", length = 32)
    private String durationClass;

    /** 画面描述（视觉增强填充，未增强时为 null） */
    @Column(length = 2000)
    private String description;

    /** 景别（视觉增强填充） */
    @Column(name = "shot_size_label", length = 32)
    private String shotSizeLabel;

    /** 运镜（视觉增强填充） */
    @Column(name = "camera_move_label", length = 32)
    private String cameraMoveLabel;

    /** 反推提示词（通用版） */
    @Column(name = "prompt_generic", columnDefinition = "CLOB")
    private String promptGeneric;

    /** 反推提示词（Seedance 风格字段版） */
    @Column(name = "prompt_seedance", columnDefinition = "CLOB")
    private String promptSeedance;

    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public Long getDeconstructionId() {
        return deconstructionId;
    }

    public void setDeconstructionId(Long deconstructionId) {
        this.deconstructionId = deconstructionId;
    }

    public Integer getShotNo() {
        return shotNo;
    }

    public void setShotNo(Integer shotNo) {
        this.shotNo = shotNo;
    }

    public Double getStartSec() {
        return startSec;
    }

    public void setStartSec(Double startSec) {
        this.startSec = startSec;
    }

    public Double getEndSec() {
        return endSec;
    }

    public void setEndSec(Double endSec) {
        this.endSec = endSec;
    }

    public Double getDurationSec() {
        return durationSec;
    }

    public void setDurationSec(Double durationSec) {
        this.durationSec = durationSec;
    }

    public String getKeyframePath() {
        return keyframePath;
    }

    public void setKeyframePath(String keyframePath) {
        this.keyframePath = keyframePath;
    }

    public String getSegmentRole() {
        return segmentRole;
    }

    public void setSegmentRole(String segmentRole) {
        this.segmentRole = segmentRole;
    }

    public String getDurationClass() {
        return durationClass;
    }

    public void setDurationClass(String durationClass) {
        this.durationClass = durationClass;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public String getShotSizeLabel() {
        return shotSizeLabel;
    }

    public void setShotSizeLabel(String shotSizeLabel) {
        this.shotSizeLabel = shotSizeLabel;
    }

    public String getCameraMoveLabel() {
        return cameraMoveLabel;
    }

    public void setCameraMoveLabel(String cameraMoveLabel) {
        this.cameraMoveLabel = cameraMoveLabel;
    }

    public String getPromptGeneric() {
        return promptGeneric;
    }

    public void setPromptGeneric(String promptGeneric) {
        this.promptGeneric = promptGeneric;
    }

    public String getPromptSeedance() {
        return promptSeedance;
    }

    public void setPromptSeedance(String promptSeedance) {
        this.promptSeedance = promptSeedance;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
