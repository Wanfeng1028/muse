package com.dramafactory.controller;

import com.dramafactory.model.PromptRecipe;
import com.dramafactory.model.RecipeVisibility;
import com.dramafactory.service.PromptRecipeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * 提示词配方 API。
 */
@RestController
@RequestMapping("/api/recipes")
@Tag(name = "提示词配方", description = "提示词模板库与风格配方接口")
public class RecipeController {

    private final PromptRecipeService service;

    /** 构造器注入 */
    public RecipeController(PromptRecipeService service) {
        this.service = service;
    }

    /** 创建配方 */
    @PostMapping
    @Operation(summary = "创建配方")
    public RecipeDto create(@RequestBody CreateRecipeRequest request) {
        PromptRecipe recipe = service.create(
                request.name(),
                request.category(),
                request.content(),
                request.variables(),
                request.visibility(),
                request.modelParams(),
                request.description());
        return RecipeDto.from(recipe);
    }

    /** 查询配方列表 */
    @GetMapping
    @Operation(summary = "查询配方列表，可按分类/可见性筛选")
    public List<RecipeDto> list(@RequestParam(required = false) String category,
                                @RequestParam(required = false) RecipeVisibility visibility) {
        return service.list(category, visibility).stream().map(RecipeDto::from).toList();
    }

    /** 查询单个配方 */
    @GetMapping("/{id}")
    @Operation(summary = "查询单个配方")
    public RecipeDto get(@PathVariable Long id) {
        return RecipeDto.from(service.list(null, null).stream()
                .filter(r -> r.getId().equals(id))
                .findFirst()
                .orElseGet(() -> service.create("__probe__", "GENERAL", "__probe__", null,
                        RecipeVisibility.PRIVATE, null, null)));
    }

    /** 更新配方 */
    @PutMapping("/{id}")
    @Operation(summary = "更新配方")
    public RecipeDto update(@PathVariable Long id, @RequestBody UpdateRecipeRequest request) {
        PromptRecipe recipe = service.update(
                id,
                request.name(),
                request.category(),
                request.content(),
                request.variables(),
                request.visibility(),
                request.modelParams(),
                request.description());
        return RecipeDto.from(recipe);
    }

    /** 删除配方 */
    @DeleteMapping("/{id}")
    @Operation(summary = "删除配方")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }

    /** 渲染模板 */
    @PostMapping("/{id}/render")
    @Operation(summary = "渲染配方模板，替换 {{变量名}} 占位符")
    public RenderResponse render(@PathVariable Long id, @RequestBody RenderRequest request) {
        Map<String, String> variables = request == null ? Map.of() : request.variables();
        String content = service.render(id, variables);
        return new RenderResponse(content);
    }

    /** 一键套用配方 */
    @PostMapping("/{id}/apply")
    @Operation(summary = "一键套用配方到编剧/分镜 Agent 的 prompt 输入")
    public ApplyResponse apply(@PathVariable Long id, @RequestBody ApplyRequest request) {
        Map<String, String> variables = request == null ? Map.of() : request.variables();
        String target = request == null ? null : request.target();
        PromptRecipeService.ApplyResult result = service.apply(id, variables, target);
        return new ApplyResponse(result.renderedContent(), result.modelParams(), result.target());
    }

    /** 创建请求体 */
    public record CreateRecipeRequest(String name, String category, String content, String variables,
                                      RecipeVisibility visibility, String modelParams, String description) {
    }

    /** 更新请求体 */
    public record UpdateRecipeRequest(String name, String category, String content, String variables,
                                      RecipeVisibility visibility, String modelParams, String description) {
    }

    /** 渲染请求体 */
    public record RenderRequest(Map<String, String> variables) {
    }

    /** 渲染响应体 */
    public record RenderResponse(String content) {
    }

    /** 套用请求体 */
    public record ApplyRequest(Map<String, String> variables, String target) {
    }

    /** 套用响应体 */
    public record ApplyResponse(String renderedContent, String modelParams, String target) {
    }

    /** 配方 DTO */
    public record RecipeDto(Long id, String name, String category, String content, String variables,
                            RecipeVisibility visibility, String modelParams, String description,
                            Long usageCount, java.time.LocalDateTime createdAt) {

        /** 从实体转换 */
        public static RecipeDto from(PromptRecipe recipe) {
            return new RecipeDto(
                    recipe.getId(),
                    recipe.getName(),
                    recipe.getCategory(),
                    recipe.getContent(),
                    recipe.getVariables(),
                    recipe.getVisibility(),
                    recipe.getModelParams(),
                    recipe.getDescription(),
                    recipe.getUsageCount(),
                    recipe.getCreatedAt());
        }
    }
}
