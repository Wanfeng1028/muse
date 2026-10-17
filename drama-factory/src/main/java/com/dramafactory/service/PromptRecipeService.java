package com.dramafactory.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.PromptRecipe;
import com.dramafactory.model.RecipeVisibility;
import com.dramafactory.repository.PromptRecipeRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 提示词配方服务：CRUD、渲染与一键套用。
 */
@Service
public class PromptRecipeService {

    private static final Set<String> VALID_CATEGORIES = Set.of("SCRIPT", "BOARD", "STYLE", "GENERAL");
    private static final Set<String> VALID_TARGETS = Set.of("SCRIPT", "BOARD");
    private static final Pattern VARIABLE_PATTERN = Pattern.compile("\\{\\{([^}]+)}}");

    private final PromptRecipeRepository repository;

    /** 构造器注入 */
    public PromptRecipeService(PromptRecipeRepository repository) {
        this.repository = repository;
    }

    /**
     * 创建配方。
     *
     * @param name        名称，不可空
     * @param category    分类，必须为 SCRIPT/BOARD/STYLE/GENERAL
     * @param content     模板内容，不可空
     * @param variables   变量名列表（逗号分隔），可空
     * @param visibility  可见性
     * @param modelParams 模型参数 JSON，可空
     * @param description 说明，可空
     * @return 保存后的实体
     */
    public PromptRecipe create(String name, String category, String content, String variables,
                               RecipeVisibility visibility, String modelParams, String description) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("配方名称不能为空");
        }
        if (content == null || content.isBlank()) {
            throw new IllegalArgumentException("配方内容不能为空");
        }
        validateCategory(category);

        PromptRecipe recipe = new PromptRecipe();
        recipe.setName(name);
        recipe.setCategory(category);
        recipe.setContent(content);
        recipe.setVariables(variables);
        recipe.setVisibility(visibility == null ? RecipeVisibility.PUBLIC : visibility);
        recipe.setModelParams(modelParams);
        recipe.setDescription(description);
        recipe.setUsageCount(0L);
        return repository.save(recipe);
    }

    /**
     * 更新配方。
     *
     * @param id          配方 ID
     * @param name        名称
     * @param category    分类
     * @param content     内容
     * @param variables   变量名列表
     * @param visibility  可见性
     * @param modelParams 模型参数
     * @param description 说明
     * @return 更新后的实体
     */
    public PromptRecipe update(Long id, String name, String category, String content, String variables,
                               RecipeVisibility visibility, String modelParams, String description) {
        PromptRecipe recipe = getOrThrow(id);
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("配方名称不能为空");
        }
        if (content == null || content.isBlank()) {
            throw new IllegalArgumentException("配方内容不能为空");
        }
        validateCategory(category);

        recipe.setName(name);
        recipe.setCategory(category);
        recipe.setContent(content);
        recipe.setVariables(variables);
        if (visibility != null) {
            recipe.setVisibility(visibility);
        }
        recipe.setModelParams(modelParams);
        recipe.setDescription(description);
        return repository.save(recipe);
    }

    /**
     * 删除配方。
     *
     * @param id 配方 ID
     */
    public void delete(Long id) {
        PromptRecipe recipe = getOrThrow(id);
        repository.delete(recipe);
    }

    /**
     * 按分类/可见性筛选，均按 usageCount 倒序。
     *
     * @param category   分类，可为 null
     * @param visibility 可见性，可为 null
     * @return 配方列表
     */
    public List<PromptRecipe> list(String category, RecipeVisibility visibility) {
        if (category != null && visibility != null) {
            return repository.findByCategoryAndVisibilityOrderByUsageCountDesc(category, visibility);
        }
        if (category != null) {
            return repository.findByCategoryOrderByUsageCountDesc(category);
        }
        if (visibility != null) {
            return repository.findByVisibilityOrderByUsageCountDesc(visibility);
        }
        List<PromptRecipe> all = new ArrayList<>(repository.findAll());
        all.sort((a, b) -> Long.compare(
                b.getUsageCount() == null ? 0L : b.getUsageCount(),
                a.getUsageCount() == null ? 0L : a.getUsageCount()));
        return all;
    }

    /**
     * 渲染模板：把 {{变量名}} 替换为对应值。
     *
     * @param id        配方 ID
     * @param variables 变量映射
     * @return 渲染后的文本
     */
    public String render(Long id, Map<String, String> variables) {
        PromptRecipe recipe = getOrThrow(id);
        return doRender(recipe, variables);
    }

    /**
     * 一键套用：render + usageCount+1，返回渲染结果与模型参数。
     * <p>target 仅用于记录与校验（SCRIPT/BOARD），实际"套用到输入框"由前端完成。</p>
     *
     * @param id        配方 ID
     * @param variables 变量映射
     * @param target    目标：SCRIPT（编剧）/BOARD（分镜）
     * @return 套用结果
     */
    @Transactional
    public ApplyResult apply(Long id, Map<String, String> variables, String target) {
        if (target == null || !VALID_TARGETS.contains(target)) {
            throw new IllegalArgumentException("目标类型非法，必须为 SCRIPT 或 BOARD，实际：" + target);
        }
        PromptRecipe recipe = getOrThrow(id);
        String rendered = doRender(recipe, variables);
        repository.incrementUsageCount(id);
        return new ApplyResult(rendered, recipe.getModelParams(), target);
    }

    private String doRender(PromptRecipe recipe, Map<String, String> variables) {
        Map<String, String> vars = variables == null ? Map.of() : variables;
        Set<String> declared = extractVariables(recipe.getContent());
        for (String var : declared) {
            if (!vars.containsKey(var)) {
                throw new IllegalArgumentException("缺少变量：" + var);
            }
        }
        String content = recipe.getContent();
        Matcher matcher = VARIABLE_PATTERN.matcher(content);
        StringBuilder sb = new StringBuilder();
        while (matcher.find()) {
            String varName = matcher.group(1);
            String value = vars.get(varName);
            if (value == null) {
                throw new IllegalArgumentException("缺少变量：" + varName);
            }
            matcher.appendReplacement(sb, Matcher.quoteReplacement(value));
        }
        matcher.appendTail(sb);
        return sb.toString();
    }

    private PromptRecipe getOrThrow(Long id) {
        return repository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("PromptRecipe", id));
    }

    private void validateCategory(String category) {
        if (category == null || !VALID_CATEGORIES.contains(category)) {
            throw new IllegalArgumentException("分类非法，必须为 SCRIPT/BOARD/STYLE/GENERAL，实际：" + category);
        }
    }

    /**
     * 从模板内容提取 {{变量名}} 占位符（支持中文）。
     *
     * @param content 模板内容
     * @return 去重后的变量名集合
     */
    private Set<String> extractVariables(String content) {
        Set<String> result = new LinkedHashSet<>();
        if (content == null) {
            return result;
        }
        Matcher matcher = VARIABLE_PATTERN.matcher(content);
        while (matcher.find()) {
            result.add(matcher.group(1));
        }
        return result;
    }

    /**
     * 套用结果。
     *
     * @param renderedContent 渲染后文本
     * @param modelParams     模型参数 JSON
     * @param target          目标类型
     */
    public record ApplyResult(String renderedContent, String modelParams, String target) {
    }
}
