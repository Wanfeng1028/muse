package com.dramafactory.service;

import com.dramafactory.model.PromptRecipe;
import com.dramafactory.model.RecipeVisibility;
import com.dramafactory.repository.PromptRecipeRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

/**
 * PromptRecipeService 单元测试。
 */
@ExtendWith(MockitoExtension.class)
class PromptRecipeServiceTest {

    @Mock
    private PromptRecipeRepository repository;

    @InjectMocks
    private PromptRecipeService service;

    @Test
    void create_withBlankName_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.create("  ", "STYLE", "content", null, RecipeVisibility.PUBLIC, null, null));
        assertTrue(ex.getMessage().contains("名称"));
    }

    @Test
    void create_withInvalidCategory_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.create("name", "UNKNOWN", "content", null, RecipeVisibility.PUBLIC, null, null));
        assertTrue(ex.getMessage().contains("分类"));
    }

    @Test
    void render_replacesChineseVariable() {
        PromptRecipe recipe = new PromptRecipe();
        recipe.setId(1L);
        recipe.setName("n");
        recipe.setCategory("STYLE");
        recipe.setContent("你好，{{主角名}}！");
        recipe.setVisibility(RecipeVisibility.PUBLIC);
        when(repository.findById(1L)).thenReturn(Optional.of(recipe));

        String result = service.render(1L, Map.of("主角名", "张三"));
        assertEquals("你好，张三！", result);
    }

    @Test
    void render_missingVariable_throwsWithVariableName() {
        PromptRecipe recipe = new PromptRecipe();
        recipe.setId(1L);
        recipe.setCategory("STYLE");
        recipe.setContent("你好，{{主角名}}！");
        when(repository.findById(1L)).thenReturn(Optional.of(recipe));

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.render(1L, Map.of()));
        assertTrue(ex.getMessage().contains("主角名"));
    }

    @Test
    void render_supportsChineseVariableName() {
        PromptRecipe recipe = new PromptRecipe();
        recipe.setId(2L);
        recipe.setCategory("STYLE");
        recipe.setContent("场景：{{场景描述}}");
        when(repository.findById(2L)).thenReturn(Optional.of(recipe));

        String result = service.render(2L, Map.of("场景描述", "雨夜街头"));
        assertEquals("场景：雨夜街头", result);
    }

    @Test
    void apply_incrementsUsageCountAndReturnsModelParams() {
        PromptRecipe recipe = new PromptRecipe();
        recipe.setId(3L);
        recipe.setCategory("STYLE");
        recipe.setContent("{{主体}}");
        recipe.setModelParams("{\"temperature\":0.8}");
        recipe.setUsageCount(5L);
        when(repository.findById(3L)).thenReturn(Optional.of(recipe));
        when(repository.save(any(PromptRecipe.class))).thenAnswer(inv -> inv.getArgument(0));

        PromptRecipeService.ApplyResult result = service.apply(3L, Map.of("主体", "机器人"), "SCRIPT");

        assertEquals("机器人", result.renderedContent());
        assertEquals("{\"temperature\":0.8}", result.modelParams());
        assertEquals("SCRIPT", result.target());
        assertEquals(6L, recipe.getUsageCount());
    }

    @Test
    void apply_invalidTarget_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.apply(1L, Map.of(), "STYLE"));
        assertTrue(ex.getMessage().contains("目标"));
    }

    @Test
    void list_filtersByCategory() {
        PromptRecipe r = new PromptRecipe();
        r.setId(1L);
        r.setCategory("STYLE");
        r.setUsageCount(1L);
        when(repository.findByCategoryOrderByUsageCountDesc("STYLE")).thenReturn(List.of(r));

        List<PromptRecipe> result = service.list("STYLE", null);
        assertEquals(1, result.size());
        assertEquals("STYLE", result.get(0).getCategory());
    }
}
