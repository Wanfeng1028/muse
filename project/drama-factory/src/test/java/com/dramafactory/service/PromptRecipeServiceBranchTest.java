package com.dramafactory.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.PromptRecipe;
import com.dramafactory.model.RecipeVisibility;
import com.dramafactory.repository.PromptRecipeRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

// 注：L213 私有方法 extractVariables 的 content==null 防御分支在 public 路径不可达
//（create/update 均校验 content 非空），故本文件不覆盖该行，属预期遗漏。
@DataJpaTest
@Import(PromptRecipeService.class)
class PromptRecipeServiceBranchTest {

    @Autowired
    private PromptRecipeService service;

    @Autowired
    private PromptRecipeRepository repository;

    @Autowired
    private org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager em;

    private PromptRecipe createValid(String name, String category, String content,
                                     RecipeVisibility visibility) {
        return service.create(name, category, content, null, visibility, null, null);
    }

    // L48 m1c3: create name==null → IAE
    @Test
    void branch_create_nameNull_throwsIae() {
        assertThatThrownBy(() -> service.create(null, "SCRIPT", "c", null,
                RecipeVisibility.PUBLIC, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // L48 m1c3: create name 全空白 → IAE
    @Test
    void branch_create_nameBlank_throwsIae() {
        assertThatThrownBy(() -> service.create("  ", "SCRIPT", "c", null,
                RecipeVisibility.PUBLIC, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // L51 m2c2: create content==null → IAE
    @Test
    void branch_create_contentNull_throwsIae() {
        assertThatThrownBy(() -> service.create("n", "SCRIPT", null, null,
                RecipeVisibility.PUBLIC, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // L51 m2c2: create content 全空白 → IAE
    @Test
    void branch_create_contentBlank_throwsIae() {
        assertThatThrownBy(() -> service.create("n", "SCRIPT", "   ", null,
                RecipeVisibility.PUBLIC, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // L61 m1c1: create visibility==null → 保存后为 PUBLIC
    @Test
    void branch_create_visibilityNull_defaultsToPublic() {
        PromptRecipe saved = service.create("n", "SCRIPT", "c", null, null, null, null);
        assertThat(saved.getVisibility()).isEqualTo(RecipeVisibility.PUBLIC);
    }

    // L200 m1c3: create category==null → IAE
    @Test
    void branch_create_categoryNull_throwsIae() {
        assertThatThrownBy(() -> service.create("n", null, "c", null,
                RecipeVisibility.PUBLIC, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // L200 m1c3: create category 非法 → IAE
    @Test
    void branch_create_categoryBad_throwsIae() {
        assertThatThrownBy(() -> service.create("n", "BAD", "c", null,
                RecipeVisibility.PUBLIC, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // L84 m4c0: update name==null → IAE
    @Test
    void branch_update_nameNull_throwsIae() {
        PromptRecipe existing = createValid("n", "SCRIPT", "c", RecipeVisibility.PUBLIC);
        assertThatThrownBy(() -> service.update(existing.getId(), null, "SCRIPT", "c", null,
                RecipeVisibility.PUBLIC, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // L84 m4c0: update name 全空白 → IAE
    @Test
    void branch_update_nameBlank_throwsIae() {
        PromptRecipe existing = createValid("n", "SCRIPT", "c", RecipeVisibility.PUBLIC);
        assertThatThrownBy(() -> service.update(existing.getId(), " ", "SCRIPT", "c", null,
                RecipeVisibility.PUBLIC, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // L87 m4c0: update content==null → IAE
    @Test
    void branch_update_contentNull_throwsIae() {
        PromptRecipe existing = createValid("n", "SCRIPT", "c", RecipeVisibility.PUBLIC);
        assertThatThrownBy(() -> service.update(existing.getId(), "n2", "SCRIPT", null, null,
                RecipeVisibility.PUBLIC, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // L87 m4c0: update content 全空白 → IAE
    @Test
    void branch_update_contentBlank_throwsIae() {
        PromptRecipe existing = createValid("n", "SCRIPT", "c", RecipeVisibility.PUBLIC);
        assertThatThrownBy(() -> service.update(existing.getId(), "n2", "SCRIPT", "  ", null,
                RecipeVisibility.PUBLIC, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // L96 m2c0: update visibility==null → 保持原值 PRIVATE
    @Test
    void branch_update_visibilityNull_keepsOriginal() {
        PromptRecipe existing = createValid("n", "SCRIPT", "c", RecipeVisibility.PRIVATE);
        PromptRecipe updated = service.update(existing.getId(), "n2", "SCRIPT", "c2", null,
                null, null, null);
        assertThat(updated.getVisibility()).isEqualTo(RecipeVisibility.PRIVATE);
    }

    // L96 m2c0: update visibility PRIVATE → PUBLIC 正常更新
    @Test
    void branch_update_visibilityPrivateToPublic_updates() {
        PromptRecipe existing = createValid("n", "SCRIPT", "c", RecipeVisibility.PRIVATE);
        PromptRecipe updated = service.update(existing.getId(), "n2", "SCRIPT", "c2", null,
                RecipeVisibility.PUBLIC, null, null);
        assertThat(updated.getVisibility()).isEqualTo(RecipeVisibility.PUBLIC);
    }

    // L122 m1c3: list(category+visibility) 只返回匹配项
    @Test
    void branch_list_categoryAndVisibility_filtersBoth() {
        createValid("s", "SCRIPT", "c", RecipeVisibility.PUBLIC);
        createValid("b", "BOARD", "c", RecipeVisibility.PRIVATE);

        List<PromptRecipe> result = service.list("SCRIPT", RecipeVisibility.PUBLIC);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getName()).isEqualTo("s");
    }

    // L128 m1c1: list(null, PRIVATE) 只返回 PRIVATE
    @Test
    void branch_list_categoryNullVisibilityPrivate_returnsPrivate() {
        createValid("s", "SCRIPT", "c", RecipeVisibility.PUBLIC);
        createValid("b", "BOARD", "c", RecipeVisibility.PRIVATE);

        List<PromptRecipe> result = service.list(null, RecipeVisibility.PRIVATE);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getName()).isEqualTo("b");
    }

    // L125 m1c1: list("BOARD", null) 只返回 BOARD
    @Test
    void branch_list_categoryBoardVisibilityNull_returnsBoard() {
        createValid("s", "SCRIPT", "c", RecipeVisibility.PUBLIC);
        createValid("b", "BOARD", "c", RecipeVisibility.PRIVATE);

        List<PromptRecipe> result = service.list("BOARD", null);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getName()).isEqualTo("b");
    }

    // L133/134 m2c2: list(null, null) 按 usageCount 倒序，null 视作 0
    @Test
    void branch_list_all_sortsByUsageCountDescNullAsZero() {
        PromptRecipe high = createValid("high", "SCRIPT", "c", RecipeVisibility.PUBLIC);
        high.setUsageCount(5L);
        repository.save(high);

        PromptRecipe low = createValid("low", "SCRIPT", "c", RecipeVisibility.PUBLIC);
        low.setUsageCount(1L);
        repository.save(low);

        PromptRecipe nullCount = createValid("nullCount", "SCRIPT", "c", RecipeVisibility.PUBLIC);
        nullCount.setUsageCount(null);
        repository.save(nullCount);

        List<PromptRecipe> result = service.list(null, null);

        assertThat(result).extracting(PromptRecipe::getName)
                .containsExactly("high", "low", "nullCount");
    }

    // L160 m1c3: apply target==null → IAE
    @Test
    void branch_apply_targetNull_throwsIae() {
        PromptRecipe existing = createValid("n", "SCRIPT", "c", RecipeVisibility.PUBLIC);
        assertThatThrownBy(() -> service.apply(existing.getId(), Map.of(), null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // L160 m1c3: apply target 非法 → IAE
    @Test
    void branch_apply_targetBad_throwsIae() {
        PromptRecipe existing = createValid("n", "SCRIPT", "c", RecipeVisibility.PUBLIC);
        assertThatThrownBy(() -> service.apply(existing.getId(), Map.of(), "BAD"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // L160 m1c3 (else 分支): apply target=BOARD 成功
    @Test
    void branch_apply_targetBoard_succeeds() {
        PromptRecipe existing = createValid("n", "SCRIPT", "c", RecipeVisibility.PUBLIC);

        PromptRecipeService.ApplyResult result = service.apply(existing.getId(), Map.of(), "BOARD");

        assertThat(result.target()).isEqualTo("BOARD");
        assertThat(result.renderedContent()).isEqualTo("c");
    }

    // L165 m1c1: apply 时 usageCount==null → 置 1
    @Test
    void branch_apply_usageCountNull_becomesOne() {
        PromptRecipe existing = createValid("n", "SCRIPT", "c", RecipeVisibility.PUBLIC);
        existing.setUsageCount(null);
        repository.save(existing);

        service.apply(existing.getId(), Map.of(), "SCRIPT");
        em.clear();

        PromptRecipe reloaded = repository.findById(existing.getId()).orElseThrow();
        assertThat(reloaded.getUsageCount()).isEqualTo(1L);
    }

    // L172 m1c1: doRender variables==null 且模板含 {{x}} → 缺少变量 IAE
    @Test
    void branch_render_variablesNull_throwsMissingVariable() {
        PromptRecipe existing = createValid("n", "SCRIPT", "你好 {{x}}", RecipeVisibility.PUBLIC);

        assertThatThrownBy(() -> service.render(existing.getId(), null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("缺少变量");
    }

    // L185 m1c1: vars 含 key 但值为 null → IAE
    @Test
    void branch_render_variableValueNull_throwsIae() {
        PromptRecipe existing = createValid("n", "SCRIPT", "你好 {{x}}", RecipeVisibility.PUBLIC);

        Map<String, String> vars = new HashMap<>();
        vars.put("x", null);

        assertThatThrownBy(() -> service.render(existing.getId(), vars))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("缺少变量");
    }

    // L145/L147 + L188-191: render 成功替换 {{name}}
    @Test
    void branch_render_success_replacesVariable() {
        PromptRecipe existing = createValid("n", "SCRIPT", "你好，{{name}}！", RecipeVisibility.PUBLIC);

        String rendered = service.render(existing.getId(), Map.of("name", "世界"));

        assertThat(rendered).isEqualTo("你好，世界！");
    }

    // L194-196: getOrThrow 未找到 → ResourceNotFoundException
    @Test
    void branch_render_idNotFound_throwsResourceNotFound() {
        assertThatThrownBy(() -> service.render(999999L, Map.of()))
                .isInstanceOf(ResourceNotFoundException.class);
    }
}
