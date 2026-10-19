package com.dramafactory.pipeline;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.stereotype.Service;

/**
 * 流水线模板服务：负责扫描、加载、查询与校验模板。
 * <p>模板只读，启动时加载一次并缓存。</p>
 */
@Service
public class PipelineTemplateService {

    private static final String TEMPLATE_PATTERN = "classpath:pipeline-templates/*.yaml";

    private final PipelineTemplateLoader loader;
    private final Map<String, PipelineTemplate> templateCache;

    /**
     * 构造器注入并加载模板。
     *
     * @param loader 模板解析器
     */
    public PipelineTemplateService(PipelineTemplateLoader loader) {
        this.loader = loader;
        this.templateCache = loadAll();
    }

    private Map<String, PipelineTemplate> loadAll() {
        Map<String, PipelineTemplate> cache = new LinkedHashMap<>();
        PathMatchingResourcePatternResolver resolver = new PathMatchingResourcePatternResolver();
        try {
            Resource[] resources = resolver.getResources(TEMPLATE_PATTERN);
            for (Resource resource : resources) {
                if (resource == null || !resource.isReadable()) {
                    continue;
                }
                try (InputStream in = resource.getInputStream()) {
                    PipelineTemplate template = loader.load(in);
                    cache.put(template.getName(), template);
                } catch (IllegalArgumentException e) {
                    throw new IllegalStateException(
                            "加载模板失败 [" + resource.getFilename() + "]: " + e.getMessage(), e);
                }
            }
        } catch (IOException e) {
            throw new IllegalStateException("扫描模板资源失败: " + e.getMessage(), e);
        }
        return cache;
    }

    /**
     * 返回全部模板，按名称排序。
     *
     * @return 模板列表，永不为 null
     */
    public List<PipelineTemplate> listTemplates() {
        List<PipelineTemplate> list = new ArrayList<>(templateCache.values());
        list.sort(Comparator.comparing(PipelineTemplate::getName,
                Comparator.nullsLast(Comparator.naturalOrder())));
        return list;
    }

    /**
     * 按名称获取模板。
     *
     * @param name 模板名
     * @return 模板对象
     * @throws TemplateNotFoundException 当模板不存在时
     */
    public PipelineTemplate getTemplate(String name) {
        PipelineTemplate template = name == null ? null : templateCache.get(name);
        if (template == null) {
            throw new TemplateNotFoundException(name);
        }
        return template;
    }

    /**
     * 校验模板结构，返回问题列表，空列表表示通过。
     *
     * @param template 待校验模板
     * @return 问题描述列表，永不为 null
     */
    public List<String> validateTemplate(PipelineTemplate template) {
        List<String> problems = new ArrayList<>();
        if (template == null) {
            problems.add("模板为 null");
            return problems;
        }
        if (template.getName() == null || template.getName().isBlank()) {
            problems.add("模板缺少 name");
        }
        if (template.getVersion() == null || template.getVersion().isBlank()) {
            problems.add("模板缺少 version");
        }
        List<PipelineStage> stages = template.getStages();
        if (stages.isEmpty()) {
            problems.add("模板缺少 stages");
            return problems;
        }
        Set<String> producedSoFar = new LinkedHashSet<>();
        for (int i = 0; i < stages.size(); i++) {
            PipelineStage stage = stages.get(i);
            validateStage(stage, "stages[" + i + "]", problems);
            if (i > 0) {
                for (String dep : stage.getRequiredArtifactsIn()) {
                    if (!producedSoFar.contains(dep)) {
                        problems.add("阶段 '" + safeName(stage) + "' 依赖的制品 '" + dep
                                + "' 未在任何前置阶段的 produces 中声明");
                    }
                }
            }
            producedSoFar.addAll(stage.getProduces());
        }
        return problems;
    }

    private void validateStage(PipelineStage stage, String path, List<String> problems) {
        if (stage == null) {
            problems.add(path + " 为 null");
            return;
        }
        if (stage.getName() == null || stage.getName().isBlank()) {
            problems.add(path + " 缺少 name");
        }
        List<PipelineStage> subs = stage.getSubStages();
        for (int i = 0; i < subs.size(); i++) {
            validateStage(subs.get(i), path + ".subStages[" + i + "]", problems);
        }
    }

    private String safeName(PipelineStage stage) {
        return stage.getName() == null ? "<unnamed>" : stage.getName();
    }
}
