package com.dramafactory.billing;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * 成本账本条目实体，记录一次操作的成本生命周期。
 */
@Entity
@Table(name = "cost_ledger_entry")
public class CostLedgerEntry {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    /** 所属项目，null 表示跨项目条目 */
    @Column(name = "project_id")
    private Long projectId;

    @Column(length = 64)
    private String provider;

    @Column(length = 128)
    private String model;

    @Column(length = 64)
    private String operation;

    @Column(name = "estimated_usd", nullable = false)
    private double estimatedUsd;

    @Column(name = "actual_usd")
    private Double actualUsd;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private CostLedgerStatus status;

    @Column(name = "duration_ms")
    private Long durationMs;

    @Column(length = 1024)
    private String note;

    @PrePersist
    public void prePersist() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now();
        }
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public Long getProjectId() {
        return projectId;
    }

    public void setProjectId(Long projectId) {
        this.projectId = projectId;
    }

    public String getProvider() {
        return provider;
    }

    public void setProvider(String provider) {
        this.provider = provider;
    }

    public String getModel() {
        return model;
    }

    public void setModel(String model) {
        this.model = model;
    }

    public String getOperation() {
        return operation;
    }

    public void setOperation(String operation) {
        this.operation = operation;
    }

    public double getEstimatedUsd() {
        return estimatedUsd;
    }

    public void setEstimatedUsd(double estimatedUsd) {
        this.estimatedUsd = estimatedUsd;
    }

    public Double getActualUsd() {
        return actualUsd;
    }

    public void setActualUsd(Double actualUsd) {
        this.actualUsd = actualUsd;
    }

    public CostLedgerStatus getStatus() {
        return status;
    }

    public void setStatus(CostLedgerStatus status) {
        this.status = status;
    }

    public Long getDurationMs() {
        return durationMs;
    }

    public void setDurationMs(Long durationMs) {
        this.durationMs = durationMs;
    }

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}
