package com.dramafactory.tools.service;

import com.dramafactory.tools.model.ToolOpLog;
import com.dramafactory.tools.repository.ToolOpLogRepository;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

@Service
public class ToolOpLogService {

    private final ToolOpLogRepository repository;

    public ToolOpLogService(ToolOpLogRepository repository) {
        this.repository = repository;
    }

    public ToolOpLog log(String toolName, String operation, String params, String result, boolean success) {
        ToolOpLog log = new ToolOpLog();
        log.setToolName(toolName);
        log.setOperation(operation);
        log.setParams(params);
        log.setResult(result);
        log.setSuccess(success);
        log.setCreatedAt(LocalDateTime.now());
        return repository.save(log);
    }
}
