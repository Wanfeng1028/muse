package com.dramafactory.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * 媒体供应商实体，对应表 media_providers。
 * 一个供应商只保存一个密钥，不做多账号轮换。
 */
@Entity
@Table(name = "media_providers")
public class MediaProvider {

    /** 主键 */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Long id;

    /** 供应商名称 */
    @Column(name = "name", nullable = false, length = 128)
    private String name;

    /** 简介说明 */
    @Column(name = "description", columnDefinition = "CLOB")
    private String description;

    /** 密钥原文，仅服务端保存，禁止对外返回 */
    @Column(name = "api_key", length = 512)
    private String apiKey;

    /** API 地址 */
    @Column(name = "api_address", length = 512)
    private String apiAddress;

    /** 所属模块：VIDEO/IMAGE/MUSIC/TTS/AVATAR，默认 VIDEO */
    @Column(name = "module", length = 20, nullable = false)
    private String module = "VIDEO";

    /** 启用开关 */
    @Column(name = "enabled", nullable = false)
    private Boolean enabled = Boolean.TRUE;

    /** 创建时间 */
    @Column(name = "created_at")
    private LocalDateTime createdAt;

    /** 更新时间 */
    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

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

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }

    public String getApiAddress() {
        return apiAddress;
    }

    public void setApiAddress(String apiAddress) {
        this.apiAddress = apiAddress;
    }

    public String getModule() {
        return module;
    }

    public void setModule(String module) {
        this.module = module;
    }

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
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
