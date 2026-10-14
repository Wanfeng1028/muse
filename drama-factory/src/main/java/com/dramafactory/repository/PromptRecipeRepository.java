package com.dramafactory.repository;

import com.dramafactory.model.PromptRecipe;
import com.dramafactory.model.RecipeVisibility;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * 提示词配方仓库。
 */
public interface PromptRecipeRepository extends JpaRepository<PromptRecipe, Long> {

    /** 按分类查询，按使用次数倒序 */
    List<PromptRecipe> findByCategoryOrderByUsageCountDesc(String category);

    /** 按可见性查询，按使用次数倒序 */
    List<PromptRecipe> findByVisibilityOrderByUsageCountDesc(RecipeVisibility visibility);

    /** 按分类 + 可见性查询，按使用次数倒序 */
    List<PromptRecipe> findByCategoryAndVisibilityOrderByUsageCountDesc(String category, RecipeVisibility visibility);
}
