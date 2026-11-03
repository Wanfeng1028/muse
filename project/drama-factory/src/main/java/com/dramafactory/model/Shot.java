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
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * 分镜实体。
 * 一个分镜属于某一剧集（Episode），用于描述该镜头的内容、景别、运镜、时长、对白及视频生成提示词等。
 */
@Entity
@Table(name = "shots")
public class Shot {

    /** 主键 ID */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 所属剧集（多对一，懒加载） */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "episode_id", nullable = false)
    private Episode episode;

    /** 镜号，同一剧集内用于排序 */
    @Column(nullable = false)
    private Integer shotNo;

    /** 景别（枚举，字符串存储） */
    @Enumerated(EnumType.STRING)
    private ShotSize shotSize;

    /** 运镜方式（枚举，字符串存储） */
    @Enumerated(EnumType.STRING)
    private CameraMove cameraMove;

    /** 画面描述 */
    @Column(length = 2000)
    private String description;

    /** 时长秒数 */
    private Integer durationSeconds;

    /** 对白 / 旁白 */
    @Column(length = 4000)
    private String dialogue;

    /** 视频生成提示词 */
    @Column(length = 2000)
    private String videoPrompt;

    /** 首选视频提供方（doubao/novai/qwen/agnes/painted），为空时按规则自动分流 */
    @Column(length = 32)
    private String preferredProvider;

    /** 期望生成分辨率（如 720p/1080p），为空时用通道默认 */
    @Column(length = 16)
    private String resolution;

    /** 期望画面比例（如 16:9），为空时用通道默认 */
    @Column(length = 16)
    private String ratio;

    /** 是否生成音频，为空时用通道默认 */
    private Boolean generateAudio;

    /** 创建时间 */
    private LocalDateTime createdAt;

    /** 更新时间 */
    private LocalDateTime updatedAt;

    /** 无参构造 */
    public Shot() {
    }

    /** 持久化前回调：初始化创建时间与更新时间 */
    @PrePersist
    public void onCreate() {
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }

    /** 更新前回调：刷新更新时间 */
    @PreUpdate
    public void onUpdate() {
        this.updatedAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public Episode getEpisode() {
        return episode;
    }

    public void setEpisode(Episode episode) {
        this.episode = episode;
    }

    public Integer getShotNo() {
        return shotNo;
    }

    public void setShotNo(Integer shotNo) {
        this.shotNo = shotNo;
    }

    public ShotSize getShotSize() {
        return shotSize;
    }

    public void setShotSize(ShotSize shotSize) {
        this.shotSize = shotSize;
    }

    public CameraMove getCameraMove() {
        return cameraMove;
    }

    public void setCameraMove(CameraMove cameraMove) {
        this.cameraMove = cameraMove;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public Integer getDurationSeconds() {
        return durationSeconds;
    }

    public void setDurationSeconds(Integer durationSeconds) {
        this.durationSeconds = durationSeconds;
    }

    public String getDialogue() {
        return dialogue;
    }

    public void setDialogue(String dialogue) {
        this.dialogue = dialogue;
    }

    public String getVideoPrompt() {
        return videoPrompt;
    }

    public void setVideoPrompt(String videoPrompt) {
        this.videoPrompt = videoPrompt;
    }

    public String getPreferredProvider() {
        return preferredProvider;
    }

    public void setPreferredProvider(String preferredProvider) {
        this.preferredProvider = preferredProvider;
    }

    public String getResolution() {
        return resolution;
    }

    public void setResolution(String resolution) {
        this.resolution = resolution;
    }

    public String getRatio() {
        return ratio;
    }

    public void setRatio(String ratio) {
        this.ratio = ratio;
    }

    public Boolean getGenerateAudio() {
        return generateAudio;
    }

    public void setGenerateAudio(Boolean generateAudio) {
        this.generateAudio = generateAudio;
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
