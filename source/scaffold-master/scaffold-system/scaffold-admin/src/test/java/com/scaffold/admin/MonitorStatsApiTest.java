package com.scaffold.admin;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = ScaffoldAdminApplication.class, webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MonitorStatsApiTest {
    private static final ParameterizedTypeReference<Map<String, Object>> MAP = new ParameterizedTypeReference<>() {};
    private static final String MODULE = "it_stats_" + System.nanoTime();
    private static final String PROBE_IP = "10.250." + (System.nanoTime() % 200) + ".7";
    private static final String PROBE_USER = "probe_" + System.nanoTime();
    @Autowired private TestRestTemplate restTemplate;
    @Autowired private JdbcTemplate jdbc;
    @Autowired private PasswordEncoder encoder;
    private Long userId;
    private Long roleId;

    @AfterEach
    void cleanup() {
        jdbc.update("DELETE FROM sys_oper_log WHERE module = ?", MODULE);
        jdbc.update("DELETE FROM sys_login_log WHERE ip = ?", PROBE_IP);
        if (userId != null) {
            jdbc.update("DELETE FROM sys_user_role WHERE user_id = ?", userId);
            jdbc.update("DELETE FROM sys_user WHERE id = ?", userId);
        }
        if (roleId != null) {
            jdbc.update("DELETE FROM sys_role_menu WHERE role_id = ?", roleId);
            jdbc.update("DELETE FROM sys_role WHERE id = ?", roleId);
        }
    }

    @Test
    void operStatsReturnOverviewAndFullSeries() {
        insertOper(0, 1, 40);
        insertOper(0, 0, 900);
        HttpHeaders headers = headers(login("admin"));

        Map<String, Object> day = data(get("/api/monitor/oper-logs/stats", headers));
        assertThat(day).containsKeys("total", "failed", "successRate", "avgCost", "p95Cost", "activeUsers", "series");
        assertThat(((Number) day.get("failed")).longValue()).isGreaterThanOrEqualTo(1);
        assertThat(((Number) day.get("p95Cost")).longValue()).isGreaterThanOrEqualTo(40);
        assertThat(list(day.get("series"))).hasSize(24).allSatisfy(row -> assertThat(row).containsKeys("bucket", "total", "failed"));

        assertThat(list(data(get("/api/monitor/oper-logs/stats?range=7d", headers)).get("series"))).hasSize(7);
        assertThat(list(data(get("/api/monitor/oper-logs/stats?range=30d", headers)).get("series"))).hasSize(30);
        assertThat(data(get("/api/monitor/oper-logs/stats?range=unknown", headers))).containsEntry("range", "24h");
    }

    @Test
    void timelineMergesCloseOperationsIntoBlocks() {
        insertOper(0, 1, 10);
        insertOper(0, 0, 20);
        HttpHeaders headers = headers(login("admin"));

        Map<String, Object> timeline = data(get("/api/monitor/oper-logs/timeline", headers));
        assertThat(timeline.get("nowSec")).isNotNull();
        Map<String, Object> lane = list(timeline.get("lanes")).stream()
                .filter(row -> MODULE.equals(row.get("module"))).findFirst().orElseThrow();
        List<Map<String, Object>> blocks = list(lane.get("blocks"));
        assertThat(blocks).hasSize(1);
        assertThat(blocks.get(0)).containsEntry("count", 2).containsEntry("failed", 1).containsEntry("maxCost", 20)
                .containsKeys("startSec", "endSec", "ids");

        Map<String, Object> past = data(get("/api/monitor/oper-logs/timeline?date=2000-01-01", headers));
        assertThat(past.get("nowSec")).isNull();
        assertThat(list(past.get("lanes"))).isEmpty();
        assertThat(get("/api/monitor/oper-logs/timeline?date=bad", headers).getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
    }

    @Test
    void loginStatsReturnOverview() {
        Map<String, Object> stats = data(get("/api/monitor/login-logs/stats?range=7d", headers(login("admin"))));
        assertThat(stats).containsKeys("total", "failed", "successRate", "users", "ips", "series");
        assertThat(((Number) stats.get("total")).longValue()).isGreaterThanOrEqualTo(1);
        assertThat(list(stats.get("series"))).hasSize(7);
    }

    @Test
    void loginHeatmapAggregatesCellsAndFailureAnomalies() {
        for (int i = 0; i < 6; i++) {
            jdbc.update("INSERT INTO sys_login_log (username, ip, status, msg, login_time) VALUES (?, ?, 0, '密码错误', DATE_SUB(NOW(), INTERVAL ? MINUTE))",
                    PROBE_USER, PROBE_IP, i);
        }
        Map<String, Object> heat = data(get("/api/monitor/login-logs/heatmap?days=7", headers(login("admin"))));
        assertThat(heat).containsEntry("days", 7);
        assertThat(((Number) heat.get("threshold")).intValue()).isGreaterThanOrEqualTo(1);
        assertThat(list(heat.get("cells"))).isNotEmpty()
                .allSatisfy(cell -> assertThat(cell).containsKeys("dow", "hour", "total", "failed"));
        List<Map<String, Object>> anomalies = list(heat.get("anomalies"));
        assertThat(anomalies).anySatisfy(a -> {
            assertThat(a).containsEntry("kind", "ip").containsEntry("key", PROBE_IP);
            assertThat(((Number) a.get("failed")).longValue()).isGreaterThanOrEqualTo(6);
        });
        assertThat(anomalies).anySatisfy(a -> assertThat(a).containsEntry("kind", "user").containsEntry("key", PROBE_USER));
        assertThat(data(get("/api/monitor/login-logs/heatmap?days=99", headers(login("admin"))))).containsEntry("days", 30);
    }

    @Test
    void statsRequireLogPermissions() {
        HttpHeaders headers = headers(login(readOnlyFixture()));
        for (String path : List.of("/api/monitor/oper-logs/stats", "/api/monitor/oper-logs/timeline", "/api/monitor/login-logs/stats", "/api/monitor/login-logs/heatmap")) {
            assertThat(get(path, headers).getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
            assertThat(get(path, new HttpHeaders()).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        }
    }

    private void insertOper(int minutesAgo, int result, long cost) {
        jdbc.update("""
                INSERT INTO sys_oper_log (module, action, oper_name, cost, result, oper_time)
                VALUES (?, '查询', 'admin', ?, ?, DATE_SUB(NOW(), INTERVAL ? MINUTE))
                """, MODULE, cost, result, minutesAgo);
    }

    private String readOnlyFixture() {
        String name = "stats_read_" + System.nanoTime();
        jdbc.update("INSERT INTO sys_role (role_name, role_code, data_scope, status, deleted) VALUES (?, ?, 'SELF', 1, 0)", name, name);
        roleId = jdbc.queryForObject("SELECT id FROM sys_role WHERE role_code = ?", Long.class, name);
        jdbc.update("INSERT INTO sys_user (username, password, nickname, dept_id, status, deleted, create_by) VALUES (?, ?, ?, 5, 1, 0, ?)",
                name, encoder.encode("admin123"), name, name);
        userId = jdbc.queryForObject("SELECT id FROM sys_user WHERE username = ?", Long.class, name);
        jdbc.update("INSERT INTO sys_user_role (user_id, role_id) VALUES (?, ?)", userId, roleId);
        jdbc.update("INSERT INTO sys_role_menu (role_id, menu_id) VALUES (?, 101)", roleId);
        return name;
    }

    private String login(String username) { return TestAuthClient.login(restTemplate, username, "admin123"); }
    private HttpHeaders headers(String token) {
        HttpHeaders headers = new HttpHeaders(); headers.setBearerAuth(token); return headers;
    }
    private ResponseEntity<Map<String, Object>> get(String path, HttpHeaders headers) {
        return restTemplate.exchange(path, HttpMethod.GET, new HttpEntity<>(headers), MAP);
    }
    @SuppressWarnings("unchecked")
    private Map<String, Object> data(ResponseEntity<Map<String, Object>> response) {
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        return (Map<String, Object>) response.getBody().get("data");
    }
    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> list(Object value) { return (List<Map<String, Object>>) value; }
}
