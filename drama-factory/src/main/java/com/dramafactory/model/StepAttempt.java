package com.dramafactory.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import java.time.LocalDateTime;

/** 步骤执行历史实体 */
@Entity
@Table(name = "step_attempts")
public class StepAttempt {

    /** 主键标识 */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 步骤标识 */
    @Column(name = "step_id", nullable = false)
    private Long stepId;

    /** 尝试序号 */
    @Column(name = "attempt_no", nullable = false)
    private Integer attemptNo;

    /** 执行前状态 */
    @Column(name = "status_before", length = 32)
    private String statusBefore;

    /** 执行后状态 */
    @Column(name = "status_after", length = 32)
    private String statusAfter;

    /** 错误信息 */
    @Column(name = "error_message", length = 2000)
    private String errorMessage;

    /** 开始时间 */
    @Column(name = "started_at")
    private LocalDateTime startedAt;

    /** 结束时间 */
    @Column(name = "ended_at")
    private LocalDateTime endedAt;

    /** 创建时间 */
    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @PrePersist
    public void prePersist() {
        this.createdAt = LocalDateTime.now();
    }

    /** 获取主键标识 */
    public Long getId() {
        return id;
    }

    /** 设置主键标识 */
    public void setId(Long id) {
        this.id = id;
    }

    /** 获取步骤标识 */
    public Long getStepId() {
        return stepId;
    }

    /** 设置步骤标识 */
    public void setStepId(Long stepId) {
        this.stepId = stepId;
    }

    /** 获取尝试序号 */
    public Integer getAttemptNo() {
        return attemptNo;
    }

    /** 设置尝试序号 */
    public void setAttemptNo(Integer attemptNo) {
        this.attemptNo = attemptNo;
    }

    /** 获取执行前状态 */
    public String getStatusBefore() {
        return statusBefore;
    }

    /** 设置执行前状态 */
    public void setStatusBefore(String statusBefore) {
        this.statusBefore = statusBefore;
    }

    /** 获取执行后状态 */
    public String getStatusAfter() {
        return statusAfter;
    }

    /** 设置执行后状态 */
    public void setStatusAfter(String statusAfter) {
        this.statusAfter = statusAfter;
    }

    /** 获取错误信息 */
    public String getErrorMessage() {
        return errorMessage;
    }

    /** 设置错误信息 */
    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }

    /** 获取开始时间 */
    public LocalDateTime getStartedAt() {
        return startedAt;
    }

    /** 设置开始时间 */
    public void setStartedAt(LocalDateTime startedAt) {
        this.startedAt = startedAt;
    }

    /** 获取结束时间 */
    public LocalDateTime getEndedAt() {
        return endedAt;
    }

    /** 设置结束时间 */
    public void setEndedAt(LocalDateTime endedAt) {
        this.endedAt = endedAt;
    }

    /** 获取创建时间 */
    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    /** 设置创建时间 */
    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
