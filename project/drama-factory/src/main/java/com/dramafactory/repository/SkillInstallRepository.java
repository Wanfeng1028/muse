package com.dramafactory.repository;

import com.dramafactory.model.SkillInstall;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * Skill 安装记录仓库。
 */
public interface SkillInstallRepository extends JpaRepository<SkillInstall, Long> {

    /** 按 Skill 查询安装记录 */
    Optional<SkillInstall> findBySkillId(Long skillId);

    /** 查询全部安装记录，按安装时间倒序 */
    List<SkillInstall> findAllByOrderByInstalledAtDesc();
}
