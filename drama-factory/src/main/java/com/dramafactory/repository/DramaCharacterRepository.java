package com.dramafactory.repository;

import com.dramafactory.model.DramaCharacter;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface DramaCharacterRepository extends JpaRepository<DramaCharacter, Long> {

    List<DramaCharacter> findByProjectIdOrderByIdAsc(Long projectId);

    long countByProjectId(Long projectId);
}
