package com.dramafactory.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * 创作者档案实体，对应数据库表 creator_profiles。
 * <p>每位创作者在本系统中对应一条档案记录，用于维护其对外展示信息与归属关系。</p>
 * <p>创作者的 Skill 统计数据通过 Skill 实体的 author 字段进行匹配：
 * 当 Skill.author 等于本实体的 handle 或 displayName 时，该 Skill 即归属此创作者。</p>
 */
@Entity
@Table(name = "creator_profiles")
public class CreatorProfile {

    /**
     * 主键，自增 ID。
     */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * 创作者对外公开的唯一标识（slug），格式为 ^[a-z0-9-]{3,50}$，
     * 即 3 到 50 位的小写字母、数字或连字符。数据库中唯一，不允许为空。
     */
    @Column(name = "handle", nullable = false, unique = true, length = 50)
    private String handle;

    /**
     * 创作者的展示名称，对应数据库列 display_name，不允许为空，最长 100 字符。
     */
    @Column(name = "display_name", nullable = false, length = 100)
    private String displayName;

    /**
     * 创作者的个人简介，最长 500 字符，允许为空。
     */
    @Column(name = "bio", length = 500)
    private String bio;

    /**
     * 创作者的个人网站地址，最长 500 字符，允许为空。
     */
    @Column(name = "website", length = 500)
    private String website;

    /**
     * 档案所属用户的唯一标识，对应数据库列 owner_id，不允许为空，最长 128 字符。
     */
    @Column(name = "owner_id", nullable = false, length = 128)
    private String ownerId;

    /**
     * 记录创建时间，由 @PrePersist 在首次持久化时自动填充。
     */
    @Column(name = "created_at")
    private LocalDateTime createdAt;

    /**
     * 记录最后更新时间，由 @PrePersist 与 @PreUpdate 自动填充。
     */
    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    /**
     * 持久化前回调：初始化创建时间与更新时间。
     */
    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }

    /**
     * 更新前回调：刷新最后更新时间。
     */
    @PreUpdate
    protected void onUpdate() {
        this.updatedAt = LocalDateTime.now();
    }

    /**
     * 获取主键 ID。
     *
     * @return 主键 ID
     */
    public Long getId() {
        return id;
    }

    /**
     * 设置主键 ID。
     *
     * @param id 主键 ID
     */
    public void setId(Long id) {
        this.id = id;
    }

    /**
     * 获取创作者的公开 slug 标识。
     *
     * @return handle 标识
     */
    public String getHandle() {
        return handle;
    }

    /**
     * 设置创作者的公开 slug 标识。
     *
     * @param handle handle 标识，须符合 ^[a-z0-9-]{3,50}$
     */
    public void setHandle(String handle) {
        this.handle = handle;
    }

    /**
     * 获取创作者展示名称。
     *
     * @return 展示名称
     */
    public String getDisplayName() {
        return displayName;
    }

    /**
     * 设置创作者展示名称。
     *
     * @param displayName 展示名称
     */
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    /**
     * 获取个人简介。
     *
     * @return 个人简介
     */
    public String getBio() {
        return bio;
    }

    /**
     * 设置个人简介。
     *
     * @param bio 个人简介
     */
    public void setBio(String bio) {
        this.bio = bio;
    }

    /**
     * 获取个人网站地址。
     *
     * @return 个人网站地址
     */
    public String getWebsite() {
        return website;
    }

    /**
     * 设置个人网站地址。
     *
     * @param website 个人网站地址
     */
    public void setWebsite(String website) {
        this.website = website;
    }

    /**
     * 获取所属用户标识。
     *
     * @return 所属用户标识
     */
    public String getOwnerId() {
        return ownerId;
    }

    /**
     * 设置所属用户标识。
     *
     * @param ownerId 所属用户标识
     */
    public void setOwnerId(String ownerId) {
        this.ownerId = ownerId;
    }

    /**
     * 获取创建时间。
     *
     * @return 创建时间
     */
    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    /**
     * 设置创建时间。
     *
     * @param createdAt 创建时间
     */
    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    /**
     * 获取最后更新时间。
     *
     * @return 最后更新时间
     */
    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    /**
     * 设置最后更新时间。
     *
     * @param updatedAt 最后更新时间
     */
    public void setUpdatedAt(LocalDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }
}
