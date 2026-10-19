package com.dramafactory.pipeline;

/**
 * 按名称查询流水线模板时未找到对应模板所抛出的异常。
 */
public class TemplateNotFoundException extends RuntimeException {

    private final String templateName;

    /**
     * 构造异常。
     *
     * @param templateName 未找到的模板名
     */
    public TemplateNotFoundException(String templateName) {
        super("Pipeline template not found: " + templateName);
        this.templateName = templateName;
    }

    /**
     * 获取未找到的模板名。
     *
     * @return 模板名
     */
    public String getTemplateName() {
        return templateName;
    }
}
