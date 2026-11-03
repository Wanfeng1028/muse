package com.scaffold.system.service;

import com.scaffold.framework.audit.OperationLogEntry;
import com.scaffold.framework.audit.OperationLogRecorder;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class JdbcOperationLogRecorder implements OperationLogRecorder {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOperationLogRecorder(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void record(OperationLogEntry entry) {
        jdbcTemplate.update("""
                INSERT INTO sys_oper_log (module, action, request_method, request_url, request_params,
                    oper_name, dept_name, ip, location, cost, result, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                entry.module(),
                entry.action(),
                entry.requestMethod(),
                entry.requestUrl(),
                entry.requestParams(),
                entry.operator(),
                null,
                entry.ip(),
                location(entry.ip()),
                entry.cost(),
                entry.result(),
                entry.errorMessage()
        );
    }

    private String location(String ip) {
        if (ip == null || ip.isBlank()) {
            return null;
        }
        return "127.0.0.1".equals(ip) || "0:0:0:0:0:0:0:1".equals(ip) ? "本机" : "内网";
    }
}
