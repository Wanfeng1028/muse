package com.dramafactory.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * Skill 安装记录实体。
 * <p>每个 Skill 至多一条安装记录（skill_id 唯一）。</p>
 */
@Entity
@Table(name = "skill_installs")
public class SkillInstall {

    /** 主键 ID，自增 */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 已安装的 Skill ID */
    @Column(name = "skill_id", nullable = false, unique = true)
    private Long skillId;

    /** 已安装的版本号 */
    @Column(nullable = false, length = 50)
    private String version;

    /** 安装时间 */
    @Column(name = "installed_at")
    private LocalDateTime installedAt;

    /** 持久化前回调：初始化安装时间 */
    @PrePersist
    public void onCreate() {
        this.installedAt = LocalDateTime.now();
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

    public LocalDateTime getInstalledAt() {
        return installedAt;
    }

    public void setInstalledAt(LocalDateTime installedAt) {
        this.installedAt = installedAt;
    }
}
