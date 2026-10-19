package com.dramafactory.repository;

import com.dramafactory.model.ReviewItem;
import com.dramafactory.model.ReviewKind;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface ReviewItemRepository extends JpaRepository<ReviewItem, Long> {

    Optional<ReviewItem> findByEpisodeIdAndKind(Long episodeId, ReviewKind kind);

    List<ReviewItem> findByEpisodeId(Long episodeId);
}
