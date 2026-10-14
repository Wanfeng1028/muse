package com.dramafactory.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;

import java.time.LocalDateTime;

/**
 * Agent 技能实体。
 * <p>Skill 是可复用的 prompt 模板集合，支持多版本发布与市场安装。</p>
 */
@Entity
@Table(name = "skills")
public class Skill {

    /** 主键 ID，自增 */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 技能名称 */
    @Column(nullable = false, length = 200)
    private String name;

    /** 唯一标识 slug，格式 ^[a-z0-9-]{3,100}$ */
    @Column(nullable = false, unique = true, length = 200)
    private String slug;

    /** 一句话说明 */
    @Column(length = 1000)
    private String description;

    /** 作者，默认「官方」 */
    @Column(nullable = false, length = 200)
    private String author = "官方";

    /** 分类：SCRIPT/BOARD/VIDEO/EDIT/GENERAL */
    @Column(nullable = false, length = 50)
    private String category;

    /** 逗号分隔的标签 */
    @Column(length = 500)
    private String tags;

    /** 图标标识 */
    @Column(length = 50)
    private String icon;

    /** 是否官方预设 */
    @Column
    private Boolean official = Boolean.FALSE;

    /** 安装次数 */
    @Column(name = "install_count")
    private Long installCount = 0L;

    /** 评分总分 */
    @Column(name = "rating_sum")
    private Long ratingSum = 0L;

    /** 评分次数 */
    @Column(name = "rating_count")
    private Long ratingCount = 0L;

    /** 创建时间 */
    @Column(name = "created_at")
    private LocalDateTime createdAt;

    /** 更新时间 */
    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    /** 持久化前回调：初始化时间戳与默认计数 */
    @PrePersist
    public void onCreate() {
        LocalDateTime now = LocalDateTime.now();
        this.createdAt = now;
        this.updatedAt = now;
        if (this.official == null) {
            this.official = Boolean.FALSE;
        }
        if (this.installCount == null) {
            this.installCount = 0L;
        }
        if (this.ratingSum == null) {
            this.ratingSum = 0L;
        }
        if (this.ratingCount == null) {
            this.ratingCount = 0L;
        }
        if (this.author == null) {
            this.author = "官方";
        }
    }

    /** 更新前回调：刷新更新时间 */
    @PreUpdate
    public void onUpdate() {
        this.updatedAt = LocalDateTime.now();
    }

    /**
     * 计算平均评分。
     *
     * @return 评分次数大于 0 时返回保留 1 位小数的平均分，否则返回 null
     */
    @Transient
    public Double getAvgRating() {
        if (this.ratingCount == null || this.ratingCount <= 0L) {
            return null;
        }
        double avg = (double) this.ratingSum / this.ratingCount;
        return Math.round(avg * 10.0) / 10.0;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getSlug() {
        return slug;
    }

    public void setSlug(String slug) {
        this.slug = slug;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public String getAuthor() {
        return author;
    }

    public void setAuthor(String author) {
        this.author = author;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public String getTags() {
        return tags;
    }

    public void setTags(String tags) {
        this.tags = tags;
    }

    public String getIcon() {
        return icon;
    }

    public void setIcon(String icon) {
        this.icon = icon;
    }

    public Boolean getOfficial() {
        return official;
    }

    public void setOfficial(Boolean official) {
        this.official = official;
    }

    public Long getInstallCount() {
        return installCount;
    }

    public void setInstallCount(Long installCount) {
        this.installCount = installCount;
    }

    public Long getRatingSum() {
        return ratingSum;
    }

    public void setRatingSum(Long ratingSum) {
        this.ratingSum = ratingSum;
    }

    public Long getRatingCount() {
        return ratingCount;
    }

    public void setRatingCount(Long ratingCount) {
        this.ratingCount = ratingCount;
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
