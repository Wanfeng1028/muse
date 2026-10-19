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
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.time.LocalDateTime;

/**
 * 审核记录：挂在剧集上，每集每种 kind 最多一条。
 */
@Entity
@Table(name = "review_item")
public class ReviewItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // 所属剧集，多对一，延迟加载；episode 删除时级联（与 V18 的 ON DELETE CASCADE 一致）
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "episode_id", nullable = false)
    @OnDelete(action = OnDeleteAction.CASCADE)
    private Episode episode;

    // 审核对象类型：SCRIPT / BOARD
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private ReviewKind kind;

    // 当前审核状态
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private ReviewStatus status;

    @Column(length = 128)
    private String submittedBy;

    private LocalDateTime submittedAt;

    @Column(name = "l1_reviewer_id", length = 128)
    private String l1ReviewerId;

    @Column(name = "l1_reviewed_at")
    private LocalDateTime l1ReviewedAt;

    @Column(name = "l2_reviewer_id", length = 128)
    private String l2ReviewerId;

    @Column(name = "l2_reviewed_at")
    private LocalDateTime l2ReviewedAt;

    @Column(length = 1024)
    private String lastComment;

    // 乐观锁版本号
    @Version
    @Column(nullable = false)
    private int version;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;

    public ReviewItem() {
    }

    // 持久化前初始化时间戳
    @PrePersist
    public void prePersist() {
        LocalDateTime now = LocalDateTime.now();
        this.createdAt = now;
        this.updatedAt = now;
    }

    // 更新前刷新更新时间
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

    public Episode getEpisode() {
        return episode;
    }

    public void setEpisode(Episode episode) {
        this.episode = episode;
    }

    public ReviewKind getKind() {
        return kind;
    }

    public void setKind(ReviewKind kind) {
        this.kind = kind;
    }

    public ReviewStatus getStatus() {
        return status;
    }

    public void setStatus(ReviewStatus status) {
        this.status = status;
    }

    public String getSubmittedBy() {
        return submittedBy;
    }

    public void setSubmittedBy(String submittedBy) {
        this.submittedBy = submittedBy;
    }

    public LocalDateTime getSubmittedAt() {
        return submittedAt;
    }

    public void setSubmittedAt(LocalDateTime submittedAt) {
        this.submittedAt = submittedAt;
    }

    public String getL1ReviewerId() {
        return l1ReviewerId;
    }

    public void setL1ReviewerId(String l1ReviewerId) {
        this.l1ReviewerId = l1ReviewerId;
    }

    public LocalDateTime getL1ReviewedAt() {
        return l1ReviewedAt;
    }

    public void setL1ReviewedAt(LocalDateTime l1ReviewedAt) {
        this.l1ReviewedAt = l1ReviewedAt;
    }

    public String getL2ReviewerId() {
        return l2ReviewerId;
    }

    public void setL2ReviewerId(String l2ReviewerId) {
        this.l2ReviewerId = l2ReviewerId;
    }

    public LocalDateTime getL2ReviewedAt() {
        return l2ReviewedAt;
    }

    public void setL2ReviewedAt(LocalDateTime l2ReviewedAt) {
        this.l2ReviewedAt = l2ReviewedAt;
    }

    public String getLastComment() {
        return lastComment;
    }

    public void setLastComment(String lastComment) {
        this.lastComment = lastComment;
    }

    public int getVersion() {
        return version;
    }

    public void setVersion(int version) {
        this.version = version;
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
