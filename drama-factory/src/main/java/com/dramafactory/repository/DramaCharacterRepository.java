package com.dramafactory.repository;

import com.dramafactory.model.DramaCharacter;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface DramaCharacterRepository extends JpaRepository<DramaCharacter, Long> {

    List<DramaCharacter> findByProjectIdOrderByIdAsc(Long projectId);

    long countByProjectId(Long projectId);

    /**
     * 按归属用户聚合统计角色数（替代 N+1 逐项目 count）。
     */
    @org.springframework.data.jpa.repository.Query(
            "SELECT COUNT(c) FROM DramaCharacter c WHERE c.project.ownerId = :ownerId")
    long countByOwner(@org.springframework.data.repository.query.Param("ownerId") String ownerId);
}
