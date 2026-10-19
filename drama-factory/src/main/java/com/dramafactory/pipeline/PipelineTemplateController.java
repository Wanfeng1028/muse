package com.dramafactory.pipeline;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 流水线模板只读 REST 接口。
 */
@RestController
@RequestMapping("/api/pipeline-templates")
public class PipelineTemplateController {

    private final PipelineTemplateService service;

    /**
     * 构造器注入。
     *
     * @param service 模板服务
     */
    public PipelineTemplateController(PipelineTemplateService service) {
        this.service = service;
    }

    /**
     * 列出全部模板摘要。
     *
     * @return 模板摘要列表
     */
    @GetMapping
    public List<TemplateSummary> list() {
        List<TemplateSummary> summaries = new ArrayList<>();
        for (PipelineTemplate template : service.listTemplates()) {
            summaries.add(new TemplateSummary(
                    template.getName(),
                    template.getVersion(),
                    template.getCategory(),
                    template.getDescription()));
        }
        return summaries;
    }

    /**
     * 按名称获取完整模板。
     *
     * @param name 模板名
     * @return 完整模板对象
     */
    @GetMapping("/{name}")
    public PipelineTemplate get(@PathVariable String name) {
        return service.getTemplate(name);
    }

    /**
     * 处理模板未找到异常，返回 404 JSON。
     *
     * @param ex 异常
     * @return 404 响应体
     */
    @ExceptionHandler(TemplateNotFoundException.class)
    public ResponseEntity<Map<String, Object>> handleNotFound(TemplateNotFoundException ex) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("error", ex.getMessage());
        body.put("template", ex.getTemplateName());
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }

    /**
     * 模板摘要视图，避免在列表接口暴露完整 stages。
     */
    public static class TemplateSummary {
        private String name;
        private String version;
        private String category;
        private String description;

        public TemplateSummary() {
        }

        /**
         * 构造摘要。
         *
         * @param name        模板名
         * @param version     版本
         * @param category    分类
         * @param description 描述
         */
        public TemplateSummary(String name, String version, String category, String description) {
            this.name = name;
            this.version = version;
            this.category = category;
            this.description = description;
        }

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
         * 获取版本。
         *
         * @return 版本
         */
        public String getVersion() {
            return version;
        }

        /**
         * 设置版本。
         *
         * @param version 版本
         */
        public void setVersion(String version) {
            this.version = version;
        }

        /**
         * 获取分类。
         *
         * @return 分类
         */
        public String getCategory() {
            return category;
        }

        /**
         * 设置分类。
         *
         * @param category 分类
         */
        public void setCategory(String category) {
            this.category = category;
        }

        /**
         * 获取描述。
         *
         * @return 描述
         */
        public String getDescription() {
            return description;
        }

        /**
         * 设置描述。
         *
         * @param description 描述
         */
        public void setDescription(String description) {
            this.description = description;
        }
    }
}
