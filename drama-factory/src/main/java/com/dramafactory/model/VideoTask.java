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
 * 视频生成任务实体。
 * 记录某个镜头（Shot）在指定视频提供方（如 agnes / mock）上的视频生成任务状态，
 * 包括提供方任务 ID、尝试次数、重试时间、错误信息以及生成的视频地址与本地路径。
 */
@Entity
@Table(name = "video_tasks")
public class VideoTask {

    /** 主键 ID */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 关联的镜头，多对一，延迟加载，不可为空 */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "shot_id", nullable = false)
    private Shot shot;

    /** 视频提供方：agnes / mock */
    @Column(length = 50)
    private String provider;

    /** 提供方侧的任务 ID */
    @Column(length = 255)
    private String providerTaskId;

    /** 任务状态，枚举以字符串形式持久化，不可为空 */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private VideoTaskStatus status;

    /** 已尝试次数，默认 0，不可为空 */
    @Column(nullable = false)
    private Integer attempts = 0;

    /** 下次可轮询/重试的时间 */
    private LocalDateTime nextRetryAt;

    /** 错误信息，最长 2000 字符 */
    @Column(length = 2000)
    private String errorMessage;

    /** 提供方返回的视频地址，最长 1000 字符 */
    @Column(length = 1000)
    private String videoUrl;

    /** 下载到本地的片段路径，最长 1000 字符 */
    @Column(length = 1000)
    private String localPath;

    /** 创建时间 */
    private LocalDateTime createdAt;

    /** 更新时间 */
    private LocalDateTime updatedAt;

    /** 无参构造 */
    public VideoTask() {
    }

    /** 持久化前回调：初始化创建时间与更新时间 */
    @PrePersist
    public void prePersist() {
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
        if (this.attempts == null) {
            this.attempts = 0;
        }
    }

    /** 更新前回调：刷新更新时间 */
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

    public Shot getShot() {
        return shot;
    }

    public void setShot(Shot shot) {
        this.shot = shot;
    }

    public String getProvider() {
        return provider;
    }

    public void setProvider(String provider) {
        this.provider = provider;
    }

    public String getProviderTaskId() {
        return providerTaskId;
    }

    public void setProviderTaskId(String providerTaskId) {
        this.providerTaskId = providerTaskId;
    }

    public VideoTaskStatus getStatus() {
        return status;
    }

    public void setStatus(VideoTaskStatus status) {
        this.status = status;
    }

    public Integer getAttempts() {
        return attempts;
    }

    public void setAttempts(Integer attempts) {
        this.attempts = attempts;
    }

    public LocalDateTime getNextRetryAt() {
        return nextRetryAt;
    }

    public void setNextRetryAt(LocalDateTime nextRetryAt) {
        this.nextRetryAt = nextRetryAt;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }

    public String getVideoUrl() {
        return videoUrl;
    }

    public void setVideoUrl(String videoUrl) {
        this.videoUrl = videoUrl;
    }

    public String getLocalPath() {
        return localPath;
    }

    public void setLocalPath(String localPath) {
        this.localPath = localPath;
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
