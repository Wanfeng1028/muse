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
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * 审核历史：只增不删不改。
 */
@Entity
@Table(name = "review_history")
public class ReviewHistory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // 所属审核记录，多对一，延迟加载
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "review_item_id", nullable = false)
    @OnDelete(action = OnDeleteAction.CASCADE)
    private ReviewItem reviewItem;

    // 冗余存储剧集 ID，方便按集查询
    @Column(nullable = false)
    private Long episodeId;

    // 冗余存储审核对象类型
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private ReviewKind kind;

    // 流转前状态，可空
    @Enumerated(EnumType.STRING)
    @Column(length = 32)
    private ReviewStatus fromStatus;

    // 流转后状态
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private ReviewStatus toStatus;

    // 触发事件名
    @Column(nullable = false, length = 32)
    private String event;

    @Column(length = 128)
    private String actorId;

    @Column(length = 1024)
    private String comment;

    // 流转后记录的版本号
    @Column(nullable = false)
    private int itemVersionAfter;

    private LocalDateTime createdAt;

    public ReviewHistory() {
    }

    // 持久化前初始化时间戳
    @PrePersist
    public void prePersist() {
        this.createdAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public ReviewItem getReviewItem() {
        return reviewItem;
    }

    public void setReviewItem(ReviewItem reviewItem) {
        this.reviewItem = reviewItem;
    }

    public Long getEpisodeId() {
        return episodeId;
    }

    public void setEpisodeId(Long episodeId) {
        this.episodeId = episodeId;
    }

    public ReviewKind getKind() {
        return kind;
    }

    public void setKind(ReviewKind kind) {
        this.kind = kind;
    }

    public ReviewStatus getFromStatus() {
        return fromStatus;
    }

    public void setFromStatus(ReviewStatus fromStatus) {
        this.fromStatus = fromStatus;
    }

    public ReviewStatus getToStatus() {
        return toStatus;
    }

    public void setToStatus(ReviewStatus toStatus) {
        this.toStatus = toStatus;
    }

    public String getEvent() {
        return event;
    }

    public void setEvent(String event) {
        this.event = event;
    }

    public String getActorId() {
        return actorId;
    }

    public void setActorId(String actorId) {
        this.actorId = actorId;
    }

    public String getComment() {
        return comment;
    }

    public void setComment(String comment) {
        this.comment = comment;
    }

    public int getItemVersionAfter() {
        return itemVersionAfter;
    }

    public void setItemVersionAfter(int itemVersionAfter) {
        this.itemVersionAfter = itemVersionAfter;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
