package com.dramafactory.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * 提示词模板/配方实体。
 * <p>支持 {{变量名}} 占位符，可套用到编剧或分镜 Agent 的 prompt 输入框。</p>
 */
@Entity
@Table(name = "prompt_recipes")
public class PromptRecipe {

    /** 主键 ID，自增 */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 配方名称 */
    @Column(nullable = false, length = 200)
    private String name;

    /** 分类：SCRIPT（编剧）/BOARD（分镜）/STYLE（风格）/GENERAL（通用） */
    @Column(nullable = false, length = 50)
    private String category;

    /** 模板内容，支持 {{变量名}} 占位符 */
    @Lob
    @Column(nullable = false)
    private String content;

    /** 逗号分隔的变量名列表，如 "主角名,题材"，可空 */
    @Column(length = 1000)
    private String variables;

    /** 可见性：PUBLIC / PRIVATE */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private RecipeVisibility visibility = RecipeVisibility.PUBLIC;

    /** JSON 格式的模型参数配方，如 {"temperature":0.8,"style":"cyberpunk"}，可空 */
    @Column(name = "model_params", length = 2000)
    private String modelParams;

    /** 一句话说明 */
    @Column(length = 500)
    private String description;

    /** 被套用次数 */
    @Column(name = "usage_count")
    private Long usageCount = 0L;

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
        if (this.usageCount == null) {
            this.usageCount = 0L;
        }
        if (this.visibility == null) {
            this.visibility = RecipeVisibility.PUBLIC;
        }
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

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }

    public String getVariables() {
        return variables;
    }

    public void setVariables(String variables) {
        this.variables = variables;
    }

    public RecipeVisibility getVisibility() {
        return visibility;
    }

    public void setVisibility(RecipeVisibility visibility) {
        this.visibility = visibility;
    }

    public String getModelParams() {
        return modelParams;
    }

    public void setModelParams(String modelParams) {
        this.modelParams = modelParams;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public Long getUsageCount() {
        return usageCount;
    }

    public void setUsageCount(Long usageCount) {
        this.usageCount = usageCount;
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
