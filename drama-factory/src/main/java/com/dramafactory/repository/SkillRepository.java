package com.dramafactory.repository;

import com.dramafactory.model.Skill;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * Skill 仓库。
 */
public interface SkillRepository extends JpaRepository<Skill, Long> {

    /** 按 slug 查询 */
    Optional<Skill> findBySlug(String slug);

    /** 按分类查询，按安装次数倒序 */
    List<Skill> findByCategoryOrderByInstallCountDesc(String category);

    /** 根据作者查询技能列表 */
    List<Skill> findByAuthor(String author);
}
