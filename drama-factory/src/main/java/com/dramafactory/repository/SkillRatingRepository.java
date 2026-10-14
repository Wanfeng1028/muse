package com.dramafactory.repository;

import com.dramafactory.model.SkillRating;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * Skill 评分仓库。
 */
public interface SkillRatingRepository extends JpaRepository<SkillRating, Long> {

    /** 按 Skill 查询评分记录，按创建时间倒序 */
    List<SkillRating> findBySkillIdOrderByCreatedAtDesc(Long skillId);
}
