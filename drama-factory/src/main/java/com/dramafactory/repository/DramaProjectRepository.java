package com.dramafactory.repository;

import com.dramafactory.model.DramaProject;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface DramaProjectRepository extends JpaRepository<DramaProject, Long> {
}
