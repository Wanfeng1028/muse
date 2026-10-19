package com.dramafactory.pipeline;

import java.util.ArrayList;
import java.util.List;

/**
 * 模板中的单个阶段定义。
 * <p>子阶段递归复用本类型；集合字段延迟初始化，getter 绝不返回 null。</p>
 */
public class PipelineStage {

    /** 阶段名，必填 */
    private String name;

    /** 本阶段产出的制品名列表 */
    private List<String> produces = new ArrayList<>();

    /** 本阶段依赖的输入制品名列表 */
    private List<String> requiredArtifactsIn = new ArrayList<>();

    /** 是否需要检查点 */
    private boolean checkpointRequired;

    /** 是否默认需要人工审批 */
    private boolean humanApprovalDefault;

    /** 评审关注点 */
    private List<String> reviewFocus = new ArrayList<>();

    /** 成功标准 */
    private List<String> successCriteria = new ArrayList<>();

    /** 子阶段，允许递归嵌套 */
    private List<PipelineStage> subStages = new ArrayList<>();

    /**
     * 获取阶段名。
     *
     * @return 阶段名
     */
    public String getName() {
        return name;
    }

    /**
     * 设置阶段名。
     *
     * @param name 阶段名
     */
    public void setName(String name) {
        this.name = name;
    }

    /**
     * 获取产出制品名列表，永不为 null。
     *
     * @return 产出制品名列表
     */
    public List<String> getProduces() {
        if (produces == null) {
            produces = new ArrayList<>();
        }
        return produces;
    }

    /**
     * 设置产出制品名列表。
     *
     * @param produces 产出制品名列表
     */
    public void setProduces(List<String> produces) {
        this.produces = produces;
    }

    /**
     * 获取输入依赖制品名列表，永不为 null。
     *
     * @return 输入依赖制品名列表
     */
    public List<String> getRequiredArtifactsIn() {
        if (requiredArtifactsIn == null) {
            requiredArtifactsIn = new ArrayList<>();
        }
        return requiredArtifactsIn;
    }

    /**
     * 设置输入依赖制品名列表。
     *
     * @param requiredArtifactsIn 输入依赖制品名列表
     */
    public void setRequiredArtifactsIn(List<String> requiredArtifactsIn) {
        this.requiredArtifactsIn = requiredArtifactsIn;
    }

    /**
     * 是否要求检查点。
     *
     * @return true 表示需要检查点
     */
    public boolean isCheckpointRequired() {
        return checkpointRequired;
    }

    /**
     * 设置是否要求检查点。
     *
     * @param checkpointRequired 是否需要检查点
     */
    public void setCheckpointRequired(boolean checkpointRequired) {
        this.checkpointRequired = checkpointRequired;
    }

    /**
     * 是否默认需要人工审批。
     *
     * @return true 表示默认需要人工审批
     */
    public boolean isHumanApprovalDefault() {
        return humanApprovalDefault;
    }

    /**
     * 设置是否默认需要人工审批。
     *
     * @param humanApprovalDefault 是否默认需要人工审批
     */
    public void setHumanApprovalDefault(boolean humanApprovalDefault) {
        this.humanApprovalDefault = humanApprovalDefault;
    }

    /**
     * 获取评审关注点列表，永不为 null。
     *
     * @return 评审关注点列表
     */
    public List<String> getReviewFocus() {
        if (reviewFocus == null) {
            reviewFocus = new ArrayList<>();
        }
        return reviewFocus;
    }

    /**
     * 设置评审关注点列表。
     *
     * @param reviewFocus 评审关注点列表
     */
    public void setReviewFocus(List<String> reviewFocus) {
        this.reviewFocus = reviewFocus;
    }

    /**
     * 获取成功标准列表，永不为 null。
     *
     * @return 成功标准列表
     */
    public List<String> getSuccessCriteria() {
        if (successCriteria == null) {
            successCriteria = new ArrayList<>();
        }
        return successCriteria;
    }

    /**
     * 设置成功标准列表。
     *
     * @param successCriteria 成功标准列表
     */
    public void setSuccessCriteria(List<String> successCriteria) {
        this.successCriteria = successCriteria;
    }

    /**
     * 获取子阶段列表，永不为 null。
     *
     * @return 子阶段列表
     */
    public List<PipelineStage> getSubStages() {
        if (subStages == null) {
            subStages = new ArrayList<>();
        }
        return subStages;
    }

    /**
     * 设置子阶段列表。
     *
     * @param subStages 子阶段列表
     */
    public void setSubStages(List<PipelineStage> subStages) {
        this.subStages = subStages;
    }
}
