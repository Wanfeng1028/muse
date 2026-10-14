package com.dramafactory.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * Skill 版本实体。
 * <p>一个 Skill 可发布多个版本，每个版本对应一份 prompt 模板。</p>
 */
@Entity
@Table(name = "skill_versions")
public class SkillVersion {

    /** 主键 ID，自增 */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 所属 Skill ID */
    @Column(name = "skill_id", nullable = false)
    private Long skillId;

    /** 版本号，格式 ^\d+\.\d+\.\d+$ */
    @Column(nullable = false, length = 50)
    private String version;

    /** prompt 模板内容，支持 {{变量名}} 占位符 */
    @Lob
    @Column(name = "prompt_template", nullable = false)
    private String promptTemplate;

    /** 变更说明 */
    @Column(length = 1000)
    private String changelog;

    /** 创建时间 */
    @Column(name = "created_at")
    private LocalDateTime createdAt;

    /** 持久化前回调：初始化时间戳 */
    @PrePersist
    public void onCreate() {
        this.createdAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public Long getSkillId() {
        return skillId;
    }

    public void setSkillId(Long skillId) {
        this.skillId = skillId;
    }

    public String getVersion() {
        return version;
    }

    public void setVersion(String version) {
        this.version = version;
    }

    public String getPromptTemplate() {
        return promptTemplate;
    }

    public void setPromptTemplate(String promptTemplate) {
        this.promptTemplate = promptTemplate;
    }

    public String getChangelog() {
        return changelog;
    }

    public void setChangelog(String changelog) {
        this.changelog = changelog;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
