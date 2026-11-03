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
 * 成片实体，表示某集短剧最终合成输出的视频文件及其处理状态。
 */
@Entity
@Table(name = "final_cuts")
public class FinalCut {

    /** 主键 ID，自增 */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 所属剧集，多对一懒加载 */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "episode_id", nullable = false)
    private Episode episode;

    /** 成片标题 */
    private String title;

    /** 成片 mp4 文件路径 */
    @Column(length = 1000)
    private String filePath;

    /** 成片时长（秒） */
    private Double durationSeconds;

    /** 成片处理状态 */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private FinalCutStatus status;

    /** 处理失败时的错误信息 */
    @Column(length = 2000)
    private String errorMessage;

    /**
     * 质检状态：PENDING（待质检）、APPROVED（通过）、REJECTED（打回）。
     * 新建成片默认为 PENDING。
     */
    @Column(length = 20)
    private String qcStatus;

    /** 质检备注 / 打回原因 */
    @Column(length = 2000)
    private String qcNote;

    /** 质检时间 */
    private LocalDateTime qcAt;

    /** 创建时间 */
    private LocalDateTime createdAt;

    /** 更新时间 */
    private LocalDateTime updatedAt;

    /** 无参构造 */
    public FinalCut() {
    }

    /** 持久化前自动填充创建时间与更新时间，新建时质检状态默认为待质检 */
    @PrePersist
    public void onCreate() {
        LocalDateTime now = LocalDateTime.now();
        this.createdAt = now;
        this.updatedAt = now;
        if (this.qcStatus == null) {
            this.qcStatus = "PENDING";
        }
    }

    /** 更新前自动刷新更新时间 */
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

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getFilePath() {
        return filePath;
    }

    public void setFilePath(String filePath) {
        this.filePath = filePath;
    }

    public Double getDurationSeconds() {
        return durationSeconds;
    }

    public void setDurationSeconds(Double durationSeconds) {
        this.durationSeconds = durationSeconds;
    }

    public FinalCutStatus getStatus() {
        return status;
    }

    public void setStatus(FinalCutStatus status) {
        this.status = status;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }

    public String getQcStatus() {
        return qcStatus;
    }

    public void setQcStatus(String qcStatus) {
        this.qcStatus = qcStatus;
    }

    public String getQcNote() {
        return qcNote;
    }

    public void setQcNote(String qcNote) {
        this.qcNote = qcNote;
    }

    public LocalDateTime getQcAt() {
        return qcAt;
    }

    public void setQcAt(LocalDateTime qcAt) {
        this.qcAt = qcAt;
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
