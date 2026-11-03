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
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ScaffoldAdminApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class DataScopeApiTest {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_TYPE = new ParameterizedTypeReference<>() {
    };
    private static final String ADMIN123_HASH = "$2b$10$L7q28dpKkcfrrUzfvZebqe7pvxcKpaSgh7EUenf9Q5z2LiYKxDpIu";

    @Autowired
    private TestRestTemplate restTemplate;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @AfterEach
    void cleanup() {
        List<Long> userIds = jdbcTemplate.queryForList(
                "SELECT id FROM sys_user WHERE username LIKE 'scope_%'",
                Long.class
        );
        for (Long userId : userIds) {
            jdbcTemplate.update("DELETE FROM sys_user_role WHERE user_id = ?", userId);
            jdbcTemplate.update("DELETE FROM sys_user WHERE id = ?", userId);
        }
        List<Long> roleIds = jdbcTemplate.queryForList(
                "SELECT id FROM sys_role WHERE role_code LIKE 'scope_%'",
                Long.class
        );
        for (Long roleId : roleIds) {
            jdbcTemplate.update("DELETE FROM sys_role_menu WHERE role_id = ?", roleId);
            jdbcTemplate.update("DELETE FROM sys_role_dept WHERE role_id = ?", roleId);
            jdbcTemplate.update("DELETE FROM sys_role WHERE id = ?", roleId);
        }
    }

    @Test
    void selfDataScopeLimitsUserListAndExportToCurrentUser() {
        String suffix = String.valueOf(System.nanoTime());
        Long roleId = insertRole("scope_self_" + suffix, "SELF");
        insertUser("scope_self_owner_" + suffix, "本人用户", 6L, roleId);
        insertUser("scope_self_peer_" + suffix, "同部门用户", 6L, null);

        HttpHeaders headers = bearerHeaders(login("scope_self_owner_" + suffix, "admin123"));

        ResponseEntity<Map<String, Object>> users = restTemplate.exchange(
                "/api/system/users?pageNum=1&pageSize=10&keyword=scope_self_",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                MAP_TYPE
        );

        assertThat(users.getStatusCode()).isEqualTo(HttpStatus.OK);
        Map<String, Object> page = dataOf(users.getBody());
        assertThat(((Number) page.get("total")).longValue()).isEqualTo(1);
        assertThat(rowsOf(page)).extracting(row -> row.get("username"))
                .containsExactly("scope_self_owner_" + suffix);

        ResponseEntity<String> export = restTemplate.exchange(
                "/api/system/users/export?keyword=scope_self_",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );

        assertThat(export.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(export.getHeaders().getContentType()).isEqualTo(MediaType.valueOf("text/csv;charset=UTF-8"));
        assertThat(export.getBody()).contains("scope_self_owner_" + suffix);
        assertThat(export.getBody()).doesNotContain("scope_self_peer_" + suffix);
    }

    @Test
    void deptAndChildDataScopeIncludesCurrentDeptAndChildren() {
        String suffix = String.valueOf(System.nanoTime());
        Long roleId = insertRole("scope_tree_" + suffix, "DEPT_AND_CHILD");
        insertUser("scope_tree_owner_" + suffix, "部门负责人", 2L, roleId);
        insertUser("scope_tree_child_" + suffix, "子部门用户", 5L, null);
        insertUser("scope_tree_other_" + suffix, "其他部门用户", 8L, null);

        HttpHeaders headers = bearerHeaders(login("scope_tree_owner_" + suffix, "admin123"));

        ResponseEntity<Map<String, Object>> users = restTemplate.exchange(
                "/api/system/users?pageNum=1&pageSize=10&keyword=scope_tree_",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                MAP_TYPE
        );

        assertThat(users.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(rowsOf(dataOf(users.getBody()))).extracting(row -> row.get("username"))
                .containsExactly("scope_tree_owner_" + suffix, "scope_tree_child_" + suffix);
    }

    @Test
    void customDataScopeIncludesConfiguredDepartments() {
        String suffix = String.valueOf(System.nanoTime());
        Long roleId = insertRole("scope_custom_" + suffix, "CUSTOM");
        jdbcTemplate.update("INSERT INTO sys_role_dept (role_id, dept_id) VALUES (?, 8)", roleId);
        insertUser("scope_custom_owner_" + suffix, "审批专员", 6L, roleId);
        insertUser("scope_custom_allowed_" + suffix, "授权部门用户", 8L, null);
        insertUser("scope_custom_denied_" + suffix, "未授权部门用户", 11L, null);

        HttpHeaders headers = bearerHeaders(login("scope_custom_owner_" + suffix, "admin123"));

        ResponseEntity<Map<String, Object>> users = restTemplate.exchange(
                "/api/system/users?pageNum=1&pageSize=10&keyword=scope_custom_",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                MAP_TYPE
        );

        assertThat(users.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(rowsOf(dataOf(users.getBody()))).extracting(row -> row.get("username"))
                .containsExactly("scope_custom_owner_" + suffix, "scope_custom_allowed_" + suffix);
    }

    private Long insertRole(String code, String dataScope) {
        jdbcTemplate.update("""
                INSERT INTO sys_role (role_name, role_code, data_scope, sort, status, builtin, remark, create_by, update_by)
                VALUES (?, ?, ?, 99, 1, 0, '数据权限集成测试', 'it', 'it')
                """, "数据权限测试角色", code, dataScope);
        Long roleId = jdbcTemplate.queryForObject("SELECT id FROM sys_role WHERE role_code = ?", Long.class, code);
        jdbcTemplate.update("INSERT INTO sys_role_menu (role_id, menu_id) VALUES (?, 101)", roleId);
        return roleId;
    }

    private Long insertUser(String username, String nickname, Long deptId, Long roleId) {
        jdbcTemplate.update("""
                INSERT INTO sys_user (username, password, nickname, dept_id, status, deleted, create_by, update_by)
                VALUES (?, ?, ?, ?, 1, 0, 'it', 'it')
                """, username, ADMIN123_HASH, nickname, deptId);
        Long userId = jdbcTemplate.queryForObject("SELECT id FROM sys_user WHERE username = ?", Long.class, username);
        if (roleId != null) {
            jdbcTemplate.update("INSERT INTO sys_user_role (user_id, role_id) VALUES (?, ?)", userId, roleId);
        }
        return userId;
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
