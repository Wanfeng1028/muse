package com.dramafactory.tools.repository;

import com.dramafactory.tools.model.ToolOpLog;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ToolOpLogRepository extends JpaRepository<ToolOpLog, Long> {

    List<ToolOpLog> findTop50ByOrderByCreatedAtDesc();
}
