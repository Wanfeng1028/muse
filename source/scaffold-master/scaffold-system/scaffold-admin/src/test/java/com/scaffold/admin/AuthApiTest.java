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
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.Map;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ScaffoldAdminApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class AuthApiTest {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_TYPE = new ParameterizedTypeReference<>() {
    };

    @Autowired
    private TestRestTemplate restTemplate;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private PasswordEncoder passwordEncoder;

    @Test
    void loginReturnsTokenAndCurrentUserInfoUsesBearerToken() {
        String token = loginAsAdmin();

        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(token);
        ResponseEntity<Map<String, Object>> response = restTemplate.exchange(
                "/api/auth/me",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                MAP_TYPE
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        Map<String, Object> body = response.getBody();
        assertThat(body).containsEntry("code", 200);
        Map<String, Object> data = dataOf(body);
        assertThat(data).containsEntry("username", "admin");
        assertThat(data).containsEntry("nickname", "周明远");
        assertThat(listOf(data, "roles")).contains("super_admin");
        assertThat(listOf(data, "permissions")).contains("system:user:list");
    }

    @Test
    void routesReturnsAuthorizedMenuTree() {
        String token = loginAsAdmin();

        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(token);
        ResponseEntity<Map<String, Object>> response = restTemplate.exchange(
                "/api/auth/routes",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                MAP_TYPE
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        Map<String, Object> data = dataOf(response.getBody());
        assertThat((Iterable<?>) data.get("routes")).extracting("path").contains("/dashboard", "/system");
    }

    @Test
    void protectedEndpointWithoutTokenReturnsUnifiedUnauthorizedResponse() {
        ResponseEntity<Map<String, Object>> response = restTemplate.exchange(
                "/api/auth/me",
                HttpMethod.GET,
                HttpEntity.EMPTY,
                MAP_TYPE
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(response.getBody()).containsEntry("code", 401);
        assertThat(response.getBody()).containsEntry("message", "未认证或登录已过期");
        assertThat(response.getBody().get("traceId")).isNotNull();
    }

    @Test
    void logoutRevokesToken() {
        String token = loginAsAdmin();
        HttpHeaders headers = bearerHeaders(token);

        ResponseEntity<Map<String, Object>> logoutResponse = restTemplate.exchange(
                "/api/auth/logout",
                HttpMethod.POST,
                new HttpEntity<>(headers),
                MAP_TYPE
        );

        assertThat(logoutResponse.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(logoutResponse.getBody()).containsEntry("code", 200);

        ResponseEntity<Map<String, Object>> meResponse = restTemplate.exchange(
                "/api/auth/me",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                MAP_TYPE
        );

        assertThat(meResponse.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(meResponse.getBody()).containsEntry("code", 401);
    }

    @Test
    void revokedTokenCannotReadRoutes() {
        String token = loginAsAdmin();
        HttpHeaders headers = bearerHeaders(token);

        restTemplate.exchange(
                "/api/auth/logout",
                HttpMethod.POST,
                new HttpEntity<>(headers),
                MAP_TYPE
        );

        ResponseEntity<Map<String, Object>> response = restTemplate.exchange(
                "/api/auth/routes",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                MAP_TYPE
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(response.getBody()).containsEntry("message", "未认证或登录已过期");
    }

    @Test
    void loginWithWrongPasswordReturnsBusinessError() {
        ResponseEntity<Map<String, Object>> response = TestAuthClient.loginResponse(restTemplate, "admin", "bad-password");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(response.getBody()).containsEntry("code", 400);
        assertThat(response.getBody()).containsEntry("message", "账号或密码错误");
    }

    @Test
    void authenticatedUserCanChangeOwnPassword() {
        String username = "pwd_" + uniqueSuffix();
        jdbcTemplate.update("""
                        INSERT INTO sys_user (username, password, nickname, status, deleted, create_by, update_by)
                        VALUES (?, ?, ?, 1, 0, 'it', 'it')
                        """,
                username,
                passwordEncoder.encode("oldPwd123"),
                "改密测试用户"
        );
        try {
            HttpHeaders headers = bearerHeaders(login(username, "oldPwd123"));

            ResponseEntity<Map<String, Object>> response = restTemplate.exchange(
                    "/api/auth/password",
                    HttpMethod.PUT,
                    new HttpEntity<>(Map.of("oldPassword", "oldPwd123", "newPassword", "newPwd123"), headers),
                    MAP_TYPE
            );
            assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
            assertThat(response.getBody()).containsEntry("code", 200);

            ResponseEntity<Map<String, Object>> oldPasswordLogin = TestAuthClient.loginResponse(restTemplate, username, "oldPwd123");
            assertThat(oldPasswordLogin.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);

            assertThat(login(username, "newPwd123")).isNotBlank();
        } finally {
            jdbcTemplate.update("DELETE FROM sys_user WHERE username = ?", username);
        }
    }

    @Test
    void successfulLoginRecordsLastLoginTime() {
        String username = "last_" + uniqueSuffix();
        jdbcTemplate.update("""
                        INSERT INTO sys_user (username, password, nickname, status, deleted, create_by, update_by)
                        VALUES (?, ?, ?, 1, 0, 'it', 'it')
                        """,
                username,
                passwordEncoder.encode("loginPwd123"),
                "登录时间测试用户"
        );
        try {
            Integer before = jdbcTemplate.queryForObject("SELECT COUNT(*) FROM sys_user WHERE username = ? AND last_login_time IS NOT NULL", Integer.class, username);
            assertThat(before).isZero();
            assertThat(login(username, "loginPwd123")).isNotBlank();
            Integer after = jdbcTemplate.queryForObject("SELECT COUNT(*) FROM sys_user WHERE username = ? AND last_login_time IS NOT NULL", Integer.class, username);
            assertThat(after).isEqualTo(1);
        } finally {
            jdbcTemplate.update("DELETE FROM sys_user WHERE username = ?", username);
            jdbcTemplate.update("DELETE FROM sys_login_log WHERE username = ?", username);
        }
    }

    private String loginAsAdmin() {
        return login("admin", "admin123");
    }

    private String login(String username, String password) {
        return TestAuthClient.login(restTemplate, username, password);
    }

    private String uniqueSuffix() {
        return String.valueOf(System.nanoTime());
    }

    private HttpHeaders bearerHeaders(String token) {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(token);
        return headers;
    }

    @SuppressWarnings("unchecked")
    private List<Object> listOf(Map<String, Object> data, String key) {
        return (List<Object>) data.get(key);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> dataOf(Map<String, Object> body) {
        assertThat(body).containsEntry("code", 200);
        return (Map<String, Object>) body.get("data");
    }
}
