package com.dramafactory.repository;

import com.dramafactory.model.DramaProject;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface DramaProjectRepository extends JpaRepository<DramaProject, Long> {

    /** 按归属用户查项目列表：/api/projects 只走这一条，保证多用户隔离。 */
    List<DramaProject> findByOwnerId(String ownerId, Sort sort);

    /** 按归属用户计项目数：stats() 多用户口径用。 */
    long countByOwnerId(String ownerId);
}

