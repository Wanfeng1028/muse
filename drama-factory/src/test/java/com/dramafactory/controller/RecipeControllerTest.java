package com.dramafactory.controller;

import com.dramafactory.model.PromptRecipe;
import com.dramafactory.model.RecipeVisibility;
import com.dramafactory.service.PromptRecipeService;
import com.dramafactory.repository.PromptRecipeRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.when;

/**
 * RecipeController 单元测试。
 */
class RecipeControllerTest {

    private PromptRecipeRepository repository;

    private PromptRecipeService service;

    private RecipeController controller;

    @BeforeEach
    void setUp() {
        repository = Mockito.mock(PromptRecipeRepository.class);
        service = new PromptRecipeService(repository);
        controller = new RecipeController(service);
    }

    private PromptRecipe sample() {
        PromptRecipe recipe = new PromptRecipe();
        recipe.setId(1L);
        recipe.setName("赛博朋克");
        recipe.setCategory("STYLE");
        recipe.setContent("{{主体}}");
        recipe.setVariables("主体");
        recipe.setVisibility(RecipeVisibility.PUBLIC);
        recipe.setModelParams("{\"temperature\":0.85}");
        recipe.setDescription("desc");
        recipe.setUsageCount(0L);
        recipe.setCreatedAt(LocalDateTime.now());
        return recipe;
    }

    @Test
    void list_returnsDtos() {
        when(repository.findAll()).thenReturn(List.of(sample()));
        List<RecipeController.RecipeDto> result = controller.list(null, null);
        assertEquals(1, result.size());
        assertEquals("赛博朋克", result.get(0).name());
    }

    @Test
    void render_passesVariablesAndReturnsContent() {
        when(repository.findById(1L)).thenReturn(java.util.Optional.of(sample()));

        RecipeController.RenderResponse response =
                controller.render(1L, new RecipeController.RenderRequest(Map.of("主体", "机器人")));

        assertNotNull(response);
        assertEquals("机器人", response.content());
    }

    @Test
    void apply_passesVariablesAndTarget() {
        when(repository.findById(1L)).thenReturn(java.util.Optional.of(sample()));
        when(repository.save(Mockito.any(PromptRecipe.class))).thenAnswer(i -> i.getArgument(0));

        RecipeController.ApplyResponse response =
                controller.apply(1L, new RecipeController.ApplyRequest(Map.of("主体", "机器人"), "SCRIPT"));

        assertEquals("机器人", response.renderedContent());
        assertEquals("{\"temperature\":0.85}", response.modelParams());
        assertEquals("SCRIPT", response.target());
        // usageCount 自增：捕获 save 的实体断言
        org.mockito.ArgumentCaptor<PromptRecipe> captor = org.mockito.ArgumentCaptor.forClass(PromptRecipe.class);
        org.mockito.Mockito.verify(repository, org.mockito.Mockito.atLeastOnce()).save(captor.capture());
        assertEquals(1L, captor.getValue().getUsageCount());
    }

    @Test
    void create_returnsDto() {
        when(repository.save(Mockito.any(PromptRecipe.class))).thenAnswer(i -> {
            PromptRecipe r = i.getArgument(0);
            r.setId(1L);
            return r;
        });

        RecipeController.RecipeDto dto = controller.create(
                new RecipeController.CreateRecipeRequest("n", "STYLE", "{{主体}}", null,
                        RecipeVisibility.PUBLIC, null, null));

        assertEquals(1L, dto.id());
        assertEquals("n", dto.name());
    }
}
