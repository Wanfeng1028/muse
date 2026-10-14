package com.dramafactory.repository;

import com.dramafactory.model.SkillVersion;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * Skill 版本仓库。
 */
public interface SkillVersionRepository extends JpaRepository<SkillVersion, Long> {

    /** 按 Skill 查询所有版本，按创建时间倒序 */
    List<SkillVersion> findBySkillIdOrderByCreatedAtDesc(Long skillId);

    /** 按 Skill + 版本号查询 */
    Optional<SkillVersion> findBySkillIdAndVersion(Long skillId, String version);
}
