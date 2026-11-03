package com.dramafactory.repository;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import com.dramafactory.model.RunApproval;

public interface RunApprovalRepository extends JpaRepository<RunApproval, Long> {
    List<RunApproval> findByRunIdOrderByDecidedAtDesc(Long runId);
}
