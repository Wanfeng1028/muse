package com.dramafactory.pipeline;

import java.util.ArrayList;
import java.util.List;

/**
 * 流水线模板定义。
 */
public class PipelineTemplate {

    /** 模板名，必填 */
    private String name;

    /** 模板版本，必填 */
    private String version;

    /** 模板描述 */
    private String description;

    /** 模板分类 */
    private String category;

    /** 阶段列表，必填非空 */
    private List<PipelineStage> stages = new ArrayList<>();

    /**
     * 获取模板名。
     *
     * @return 模板名
     */
    public String getName() {
        return name;
    }

    /**
     * 设置模板名。
     *
     * @param name 模板名
     */
    public void setName(String name) {
        this.name = name;
    }

    /**
     * 获取模板版本。
     *
     * @return 模板版本
     */
    public String getVersion() {
        return version;
    }

    /**
     * 设置模板版本。
     *
     * @param version 模板版本
     */
    public void setVersion(String version) {
        this.version = version;
    }

    /**
     * 获取模板描述。
     *
     * @return 模板描述
     */
    public String getDescription() {
        return description;
    }

    /**
     * 设置模板描述。
     *
     * @param description 模板描述
     */
    public void setDescription(String description) {
        this.description = description;
    }

    /**
     * 获取模板分类。
     *
     * @return 模板分类
     */
    public String getCategory() {
        return category;
    }

    /**
     * 设置模板分类。
     *
     * @param category 模板分类
     */
    public void setCategory(String category) {
        this.category = category;
    }

    /**
     * 获取阶段列表，永不为 null。
     *
     * @return 阶段列表
     */
    public List<PipelineStage> getStages() {
        if (stages == null) {
            stages = new ArrayList<>();
        }
        return stages;
    }

    /**
     * 设置阶段列表。
     *
     * @param stages 阶段列表
     */
    public void setStages(List<PipelineStage> stages) {
        this.stages = stages;
    }
}
