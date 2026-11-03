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

import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = ScaffoldAdminApplication.class, webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AuthPermissionApiTest {
    private static final ParameterizedTypeReference<Map<String, Object>> MAP = new ParameterizedTypeReference<>() {};
    @Autowired private TestRestTemplate restTemplate;
    @Autowired private JdbcTemplate jdbc;
    @Autowired private PasswordEncoder encoder;
    private Long userId;
    private Long roleId;

    @AfterEach
    void cleanup() {
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
    void disabledOrDeletedRolesCannotSupplyMenusOrPermissions() {
        String username = readOnlyFixture();
        HttpHeaders headers = headers(login(username));
        assertThat(get("/api/system/users", headers).getStatusCode()).isEqualTo(HttpStatus.OK);
        for (String update : List.of("status = 0", "status = 1, deleted = 1")) {
            jdbc.update("UPDATE sys_role SET " + update + " WHERE id = ?", roleId);
            assertThat(data(get("/api/auth/me", headers)).get("permissions")).isEqualTo(List.of());
            assertThat(data(get("/api/auth/routes", headers)).get("routes")).isEqualTo(List.of());
            assertThat(get("/api/system/users", headers).getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        }
    }

    @Test
    void readOnlyUserGetsFilterOptionsWithoutManagementPermissions() {
        HttpHeaders headers = headers(login(readOnlyFixture()));
        Map<String, Object> options = data(get("/api/system/users/options", headers));
        assertThat(options).containsEntry("roles", List.of()).containsEntry("posts", List.of()).containsEntry("initPassword", "");
        assertThat((List<?>) options.get("depts")).isNotEmpty();
        assertThat(options.toString()).doesNotContain("phone", "email", "leader");
        assertThat(get("/api/system/dict/options/sys_normal_disable", headers).getStatusCode()).isEqualTo(HttpStatus.OK);
        for (String path : List.of("/api/system/roles", "/api/system/posts", "/api/system/configs", "/api/system/dict/data/sys_normal_disable")) {
            assertThat(get(path, headers).getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        }
        assertThat(restTemplate.exchange("/api/system/users", HttpMethod.POST,
                new HttpEntity<>(Map.of("username", "blocked"), headers), MAP).getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(get("/api/system/users/options", new HttpHeaders()).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(get("/api/system/dict/options/sys_normal_disable", new HttpHeaders()).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void rapidReloginDoesNotReuseARevokedToken() {
        String oldToken = login("admin");
        restTemplate.exchange("/api/auth/logout", HttpMethod.POST, new HttpEntity<>(headers(oldToken)), MAP);
        String newToken = login("admin");
        assertThat(oldToken.equals(newToken)).isFalse();
        assertThat(get("/api/auth/me", headers(oldToken)).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(get("/api/auth/me", headers(newToken)).getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void databaseSessionUsesConfiguredTimezone() {
        String zone = System.getenv().getOrDefault("DB_TIMEZONE", "+08:00");
        long expectedMinutes = OffsetDateTime.now(ZoneId.of(zone)).getOffset().getTotalSeconds() / 60;
        assertThat(jdbc.queryForObject("SELECT TIMESTAMPDIFF(MINUTE, UTC_TIMESTAMP(), NOW())", Long.class)).isEqualTo(expectedMinutes);
    }

    private String readOnlyFixture() {
        String name = "auth_read_" + System.nanoTime();
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
}
