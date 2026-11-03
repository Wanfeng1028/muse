package com.dramafactory.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

/**
 * 供应商模型配置实体，对应表 provider_models。
 * 与 MediaProvider 多对一关联，供应商删除时级联删除。
 */
@Entity
@Table(name = "provider_models")
public class ProviderModel {

    /** 主键 */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Long id;

    /** 所属供应商 */
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "provider_id", nullable = false)
    private MediaProvider provider;

    /** 模型显示名 */
    @Column(name = "display_name", nullable = false, length = 128)
    private String displayName;

    /** 模型 id */
    @Column(name = "model_id", length = 128)
    private String modelId;

    /** 规模/档位 */
    @Column(name = "scale", length = 64)
    private String scale;

    /** 文档说明 */
    @Column(name = "description", columnDefinition = "CLOB")
    private String description;

    /** 并发数 */
    @Column(name = "concurrency", nullable = false)
    private Integer concurrency = 1;

    /** 启用开关 */
    @Column(name = "enabled", nullable = false)
    private Boolean enabled = Boolean.TRUE;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public MediaProvider getProvider() {
        return provider;
    }

    public void setProvider(MediaProvider provider) {
        this.provider = provider;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getModelId() {
        return modelId;
    }

    public void setModelId(String modelId) {
        this.modelId = modelId;
    }

    public String getScale() {
        return scale;
    }

    public void setScale(String scale) {
        this.scale = scale;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public Integer getConcurrency() {
        return concurrency;
    }

    public void setConcurrency(Integer concurrency) {
        this.concurrency = concurrency;
    }

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }
}
