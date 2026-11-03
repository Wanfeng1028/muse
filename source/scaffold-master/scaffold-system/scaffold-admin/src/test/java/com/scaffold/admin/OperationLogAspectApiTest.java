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

import java.util.Map;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ScaffoldAdminApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class OperationLogAspectApiTest {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_TYPE = new ParameterizedTypeReference<>() {
    };

    @Autowired
    private TestRestTemplate restTemplate;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void annotatedWriteEndpointCreatesOperationLog() {
        String suffix = String.valueOf(System.nanoTime());
        String postName = "日志切面测试岗位" + suffix;
        HttpHeaders headers = bearerHeaders(login("admin", "admin123"));

        ResponseEntity<Map<String, Object>> create = restTemplate.exchange(
                "/api/system/posts",
                HttpMethod.POST,
                new HttpEntity<>(Map.of(
                        "postCode", "log_" + suffix,
                        "postName", postName,
                        "sort", 88,
                        "status", 1,
                        "remark", "操作日志切面测试"
                ), headers),
                MAP_TYPE
        );
        assertThat(create.getStatusCode()).isEqualTo(HttpStatus.OK);
        Long id = ((Number) dataOf(create.getBody()).get("id")).longValue();

        Map<String, Object> log = jdbcTemplate.queryForMap("""
                SELECT module, action, request_method, request_url, request_params, oper_name, result, error_msg
                FROM sys_oper_log
                WHERE module = '岗位管理' AND action = '新增' AND request_url = '/api/system/posts'
                ORDER BY id DESC
                LIMIT 1
                """);
        assertThat(log).containsEntry("module", "岗位管理");
        assertThat(log).containsEntry("action", "新增");
        assertThat(log).containsEntry("request_method", "POST");
        assertThat(log).containsEntry("request_url", "/api/system/posts");
        assertThat(log).containsEntry("oper_name", "admin");
        assertThat(((Number) log.get("result")).intValue()).isEqualTo(1);
        assertThat((String) log.get("request_params")).contains(postName);
        assertThat(log.get("error_msg")).isNull();

        ResponseEntity<Map<String, Object>> logs = restTemplate.exchange(
                "/api/monitor/oper-logs?pageNum=1&pageSize=5&keyword=" + postName,
                HttpMethod.GET,
                new HttpEntity<>(headers),
                MAP_TYPE
        );
        assertThat(logs.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(rowsOf(dataOf(logs.getBody()))).anySatisfy(row -> {
            assertThat(row).containsEntry("module", "岗位管理");
            assertThat(row).containsEntry("action", "新增");
            assertThat(row).containsEntry("url", "/api/system/posts");
        });

        restTemplate.exchange(
                "/api/system/posts/" + id,
                HttpMethod.DELETE,
                new HttpEntity<>(headers),
                MAP_TYPE
        );
    }

    @Test
    void operationLogMasksPasswordFields() {
        String suffix = String.valueOf(System.nanoTime());
        HttpHeaders headers = bearerHeaders(login("admin", "admin123"));
        Long id = createUser(headers, suffix);

        ResponseEntity<Map<String, Object>> reset = restTemplate.exchange(
                "/api/system/users/" + id + "/password",
                HttpMethod.PUT,
                new HttpEntity<>(Map.of("password", "Sensitive@123"), headers),
                MAP_TYPE
        );
        assertThat(reset.getStatusCode()).isEqualTo(HttpStatus.OK);

        String params = jdbcTemplate.queryForObject("""
                SELECT request_params
                FROM sys_oper_log
                WHERE module = '用户管理' AND action = '重置密码' AND request_url = ?
                ORDER BY id DESC
                LIMIT 1
                """, String.class, "/api/system/users/" + id + "/password");
        assertThat(params).doesNotContain("Sensitive@123");
        assertThat(params).contains("\"password\":\"******\"");

        restTemplate.exchange(
                "/api/system/users/" + id,
                HttpMethod.DELETE,
                new HttpEntity<>(headers),
                MAP_TYPE
        );
    }

    private Long createUser(HttpHeaders headers, String suffix) {
        ResponseEntity<Map<String, Object>> create = restTemplate.exchange(
                "/api/system/users",
                HttpMethod.POST,
                new HttpEntity<>(Map.of(
                        "username", "log_user_" + suffix,
                        "nickname", "日志切面用户" + suffix,
                        "password", "admin123",
                        "phone", "",
                        "email", "log_user_" + suffix + "@example.com",
                        "deptId", 6,
                        "status", 1,
                        "roleIds", List.of(4),
                        "postIds", List.of(6)
                ), headers),
                MAP_TYPE
        );
        assertThat(create.getStatusCode()).isEqualTo(HttpStatus.OK);
        return ((Number) dataOf(create.getBody()).get("id")).longValue();
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

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> rowsOf(Map<String, Object> page) {
        return (List<Map<String, Object>>) page.get("rows");
    }
}
