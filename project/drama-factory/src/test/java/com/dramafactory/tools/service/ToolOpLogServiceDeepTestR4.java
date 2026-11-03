package com.dramafactory.tools.service;

import com.dramafactory.tools.model.ToolOpLog;
import com.dramafactory.tools.repository.ToolOpLogRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ToolOpLogServiceDeepTestR4 {

    @Autowired
    private ToolOpLogService toolOpLogService;

    @Autowired
    private ToolOpLogRepository repository;

    @Test
    void log_valid_returnsSaved() {
        String toolName = "t1-" + System.nanoTime();
        ToolOpLog saved = toolOpLogService.log(toolName, "op", "p", "r", true);
        assertNotNull(saved);
        assertNotNull(saved.getId());
        assertEquals(toolName, saved.getToolName());
        assertEquals("op", saved.getOperation());
        assertEquals("p", saved.getParams());
        assertEquals("r", saved.getResult());
        assertNotNull(saved.getCreatedAt());
    }

    @Test
    void log_failedCase_saves() {
        String toolName = "t2-" + System.nanoTime();
        ToolOpLog saved = toolOpLogService.log(toolName, "op", "p", "r", false);
        assertNotNull(saved);
        assertNotNull(saved.getId());
        assertEquals(toolName, saved.getToolName());
    }

    @Test
    void log_nullParams_saves() {
        String toolName = "t3-" + System.nanoTime();
        ToolOpLog saved = toolOpLogService.log(toolName, "op", null, "r", true);
        assertNotNull(saved);
        assertNotNull(saved.getId());
        assertEquals(toolName, saved.getToolName());
        assertNull(saved.getParams());
    }

    @Test
    void log_emptyStrings_saves() {
        String toolName = "t4-" + System.nanoTime();
        ToolOpLog saved = toolOpLogService.log(toolName, "", "", "", true);
        assertNotNull(saved);
        assertNotNull(saved.getId());
        assertEquals(toolName, saved.getToolName());
        assertEquals("", saved.getOperation());
        assertEquals("", saved.getParams());
        assertEquals("", saved.getResult());
    }

    @Test
    void log_longResult_saves() {
        String toolName = "t5-" + System.nanoTime();
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 500; i++) {
            sb.append('x');
        }
        String longResult = sb.toString();
        ToolOpLog saved = toolOpLogService.log(toolName, "op", "p", longResult, true);
        assertNotNull(saved);
        assertNotNull(saved.getId());
        assertEquals(longResult, saved.getResult());
        assertEquals(500, saved.getResult().length());
    }

    @Test
    void log_twice_idsDifferent() {
        String toolName = "t6-" + System.nanoTime();
        ToolOpLog first = toolOpLogService.log(toolName, "op", "p", "r", true);
        ToolOpLog second = toolOpLogService.log(toolName, "op", "p", "r", true);
        assertNotNull(first.getId());
        assertNotNull(second.getId());
        assertTrue(second.getId() > first.getId());
    }

    @Test
    void log_thenFindTop50_contains() {
        String toolName = "t7-" + System.nanoTime();
        toolOpLogService.log(toolName, "op", "p", "r", true);
        List<ToolOpLog> logs = repository.findTop50ByOrderByCreatedAtDesc();
        boolean found = false;
        for (ToolOpLog log : logs) {
            if (toolName.equals(log.getToolName())) {
                found = true;
                break;
            }
        }
        assertTrue(found);
    }

    @Test
    void log_createdAt_isRecent() {
        String toolName = "t8-" + System.nanoTime();
        LocalDateTime before = LocalDateTime.now().minusMinutes(1);
        ToolOpLog saved = toolOpLogService.log(toolName, "op", "p", "r", true);
        LocalDateTime after = LocalDateTime.now().plusMinutes(1);
        assertNotNull(saved.getCreatedAt());
        assertTrue(saved.getCreatedAt().isAfter(before));
        assertTrue(saved.getCreatedAt().isBefore(after));
    }

    @Test
    void log_specialChars_saves() {
        String toolName = "t9-" + System.nanoTime();
        String params = "ids=3,mode=merge,备注=测试";
        ToolOpLog saved = toolOpLogService.log(toolName, "op", params, "r", true);
        assertNotNull(saved);
        assertNotNull(saved.getId());
        assertEquals(params, saved.getParams());
    }

    @Test
    void log_resultNull_saves() {
        String toolName = "t10-" + System.nanoTime();
        ToolOpLog saved = toolOpLogService.log(toolName, "op", "p", null, true);
        assertNotNull(saved);
        assertNotNull(saved.getId());
        assertEquals(toolName, saved.getToolName());
        assertNull(saved.getResult());
    }
}