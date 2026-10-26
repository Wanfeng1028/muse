package com.dramafactory.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.time.LocalDateTime;

/**
 * 创作者关注关系实体，对应数据表 creator_follows。
 * <p>记录某位关注者对某个创作者的关注关系，同一关注者对同一创作者最多只允许关注一次，
 * 由 (creator_id, follower_id) 上的唯一约束保证。</p>
 * <p>followerId 来源于 {@code CurrentUser}（开放模式下默认为 "local"）。</p>
 *
 * @author dramafactory
 */
@Entity
@Table(name = "creator_follows", uniqueConstraints = {
        @UniqueConstraint(name = "uk_creator_follows_creator_follower",
                columnNames = {"creator_id", "follower_id"})
})
public class CreatorFollow {

    /**
     * 主键，数据库自增。
     */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * 被关注的创作者 ID，对应列 creator_id，不允许为空。
     */
    @Column(name = "creator_id", nullable = false)
    private Long creatorId;

    /**
     * 关注者标识，来源于 CurrentUser（开放模式下默认为 "local"）。
     * 对应列 follower_id，不允许为空，最长 128 字符。
     */
    @Column(name = "follower_id", nullable = false, length = 128)
    private String followerId;

    /**
     * 关注时间，对应列 created_at，实体首次持久化时自动填充。
     */
    @Column(name = "created_at")
    private LocalDateTime createdAt;

    /**
     * 获取主键。
     *
     * @return 主键
     */
    public Long getId() {
        return id;
    }

    /**
     * 设置主键。
     *
     * @param id 主键
     */
    public void setId(Long id) {
        this.id = id;
    }

    /**
     * 获取被关注的创作者 ID。
     *
     * @return 被关注的创作者 ID
     */
    public Long getCreatorId() {
        return creatorId;
    }

    /**
     * 设置被关注的创作者 ID。
     *
     * @param creatorId 被关注的创作者 ID
     */
    public void setCreatorId(Long creatorId) {
        this.creatorId = creatorId;
    }

    /**
     * 获取关注者标识。
     *
     * @return 关注者标识
     */
    public String getFollowerId() {
        return followerId;
    }

    /**
     * 设置关注者标识。
     *
     * @param followerId 关注者标识
     */
    public void setFollowerId(String followerId) {
        this.followerId = followerId;
    }

    /**
     * 获取关注时间。
     *
     * @return 关注时间
     */
    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    /**
     * 设置关注时间。
     *
     * @param createdAt 关注时间
     */
    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    /**
     * 实体持久化前的回调，若关注时间为空则自动填充为当前时间。
     */
    @PrePersist
    public void prePersist() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now();
        }
    }
}
