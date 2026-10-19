package com.dramafactory.repository;

import com.dramafactory.model.ReviewHistory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface ReviewHistoryRepository extends JpaRepository<ReviewHistory, Long> {

    Page<ReviewHistory> findByReviewItemIdOrderByCreatedAtAsc(Long reviewItemId, Pageable pageable);

    List<ReviewHistory> findByReviewItemIdOrderByCreatedAtAsc(Long reviewItemId);
}
