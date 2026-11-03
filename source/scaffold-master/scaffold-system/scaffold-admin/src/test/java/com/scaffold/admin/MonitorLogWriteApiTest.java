package com.scaffold.admin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ScaffoldAdminApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class MonitorLogWriteApiTest {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_TYPE = new ParameterizedTypeReference<>() {
    };

    @Autowired
    private TestRestTemplate restTemplate;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void monitorLogDeleteAndClearPersistToDatabase() {
        HttpHeaders headers = bearerHeaders(login("admin", "admin123"));
        String suffix = String.valueOf(System.nanoTime());
        Long operId = insertOperLog("集成测试模块-" + suffix);
        Long loginId = insertLoginLog("it_login_" + suffix);

        ResponseEntity<Map<String, Object>> deleteOper = restTemplate.exchange(
                "/api/monitor/oper-logs/" + operId,
                HttpMethod.DELETE,
                new HttpEntity<>(null, headers),
                MAP_TYPE
        );
        assertThat(deleteOper.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(countById("sys_oper_log", operId)).isZero();

        ResponseEntity<Map<String, Object>> deleteLogin = restTemplate.exchange(
                "/api/monitor/login-logs/" + loginId,
                HttpMethod.DELETE,
                new HttpEntity<>(null, headers),
                MAP_TYPE
        );
        assertThat(deleteLogin.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(countById("sys_login_log", loginId)).isZero();

        insertOperLog("集成测试清空-" + suffix);
        insertLoginLog("it_clear_" + suffix);

        ResponseEntity<Map<String, Object>> clearOper = restTemplate.exchange(
                "/api/monitor/oper-logs",
                HttpMethod.DELETE,
                new HttpEntity<>(null, headers),
                MAP_TYPE
        );
        assertThat(clearOper.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(jdbcTemplate.queryForObject("SELECT COUNT(*) FROM sys_oper_log", Long.class)).isZero();

        ResponseEntity<Map<String, Object>> clearLogin = restTemplate.exchange(
                "/api/monitor/login-logs",
                HttpMethod.DELETE,
                new HttpEntity<>(null, headers),
                MAP_TYPE
        );
        assertThat(clearLogin.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(jdbcTemplate.queryForObject("SELECT COUNT(*) FROM sys_login_log", Long.class)).isZero();
    }

    @Test
    void monitorLogsCanBeExportedAsCsv() {
        HttpHeaders headers = bearerHeaders(login("admin", "admin123"));
        String suffix = String.valueOf(System.nanoTime());
        String module = "导出测试模块-" + suffix;
        String username = "export_user_" + suffix;
        insertOperLog(module);
        insertLoginLog(username);

        ResponseEntity<String> operExport = restTemplate.exchange(
                "/api/monitor/oper-logs/export?keyword=" + module,
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );
        assertThat(operExport.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(operExport.getHeaders().getContentType()).isEqualTo(MediaType.valueOf("text/csv;charset=UTF-8"));
        assertThat(operExport.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION)).contains("oper-logs");
        assertThat(operExport.getBody()).contains("模块,类型,请求方式,请求地址,请求参数,操作人,部门,IP,地点,耗时,结果,操作时间,异常信息");
        assertThat(operExport.getBody()).contains(module);

        ResponseEntity<String> loginExport = restTemplate.exchange(
                "/api/monitor/login-logs/export?keyword=" + username,
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );
        assertThat(loginExport.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(loginExport.getHeaders().getContentType()).isEqualTo(MediaType.valueOf("text/csv;charset=UTF-8"));
        assertThat(loginExport.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION)).contains("login-logs");
        assertThat(loginExport.getBody()).contains("登录账号,IP,地点,浏览器,系统,状态,描述,登录时间");
        assertThat(loginExport.getBody()).contains(username);
    }

    @Test
    void operLogExportIncludesRequestParamsWhenKeywordMatchesParams() {
        HttpHeaders headers = bearerHeaders(login("admin", "admin123"));
        String suffix = "params_" + System.nanoTime();
        insertOperLogWithParams("参数导出测试", "{\"keyword\":\"" + suffix + "\"}");

        ResponseEntity<String> operExport = restTemplate.exchange(
                "/api/monitor/oper-logs/export?keyword=" + suffix,
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );

        assertThat(operExport.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(operExport.getBody()).contains("请求参数");
        assertThat(operExport.getBody()).contains(suffix);
    }

    private Long insertOperLog(String module) {
        jdbcTemplate.update("""
                INSERT INTO sys_oper_log (module, action, request_method, request_url, request_params,
                    oper_name, dept_name, ip, location, cost, result)
                VALUES (?, 'DELETE', 'DELETE', '/api/test', '{}', 'admin', '研发中心', '127.0.0.1', '本机', 12, 1)
                """, module);
        return jdbcTemplate.queryForObject("SELECT id FROM sys_oper_log WHERE module = ?", Long.class, module);
    }

    private Long insertOperLogWithParams(String module, String params) {
        jdbcTemplate.update("""
                INSERT INTO sys_oper_log (module, action, request_method, request_url, request_params,
                    oper_name, dept_name, ip, location, cost, result)
                VALUES (?, 'POST', 'POST', '/api/test/params', ?, 'admin', '研发中心', '127.0.0.1', '本机', 12, 1)
                """, module, params);
        return jdbcTemplate.queryForObject("SELECT id FROM sys_oper_log WHERE request_params = ?", Long.class, params);
    }

    private Long insertLoginLog(String username) {
        jdbcTemplate.update("""
                INSERT INTO sys_login_log (username, ip, location, browser, os, status, msg)
                VALUES (?, '127.0.0.1', '本机', 'JUnit', 'macOS', 1, '集成测试登录日志')
                """, username);
        return jdbcTemplate.queryForObject("SELECT id FROM sys_login_log WHERE username = ?", Long.class, username);
    }

    private long countById(String tableName, Long id) {
        return jdbcTemplate.queryForObject("SELECT COUNT(*) FROM " + tableName + " WHERE id = ?", Long.class, id);
    }

    private String login(String username, String password) {
        return TestAuthClient.login(restTemplate, username, password);
    }

    private HttpHeaders bearerHeaders(String token) {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(token);
        return headers;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> dataOf(Map<String, Object> body) {
        assertThat(body).containsEntry("code", 200);
        return (Map<String, Object>) body.get("data");
    }
}
