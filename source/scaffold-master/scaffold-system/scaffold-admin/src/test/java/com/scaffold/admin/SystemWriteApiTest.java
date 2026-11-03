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

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ScaffoldAdminApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class SystemWriteApiTest {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_TYPE = new ParameterizedTypeReference<>() {
    };

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void backendPermissionAnnotationRejectsUserWithoutPermission() {
        HttpHeaders headers = bearerHeaders(login("chensy", "admin123"));

        ResponseEntity<Map<String, Object>> response = restTemplate.exchange(
                "/api/system/users",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                MAP_TYPE
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(response.getBody()).containsEntry("code", 403);
        assertThat(response.getBody()).containsEntry("message", "没有访问权限");
    }

    @Test
    void postCrudPersistsAndSoftDeletesRecord() {
        String suffix = uniqueSuffix();
        HttpHeaders headers = bearerHeaders(login("admin", "admin123"));
        Map<String, Object> createBody = Map.of(
                "postCode", "qa_" + suffix,
                "postName", "测试岗位" + suffix,
                "sort", 99,
                "status", 1,
                "remark", "集成测试创建"
        );

        ResponseEntity<Map<String, Object>> create = restTemplate.exchange(
                "/api/system/posts",
                HttpMethod.POST,
                new HttpEntity<>(createBody, headers),
                MAP_TYPE
        );
        assertThat(create.getStatusCode()).isEqualTo(HttpStatus.OK);
        Long id = ((Number) dataOf(create.getBody()).get("id")).longValue();

        ResponseEntity<Map<String, Object>> update = restTemplate.exchange(
                "/api/system/posts/" + id,
                HttpMethod.PUT,
                new HttpEntity<>(Map.of("postName", "测试岗位已更新" + suffix, "sort", 100, "status", 0, "remark", "已更新"), headers),
                MAP_TYPE
        );
        assertThat(update.getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<Map<String, Object>> list = restTemplate.exchange(
                "/api/system/posts?pageNum=1&pageSize=10&keyword=" + suffix,
                HttpMethod.GET,
                new HttpEntity<>(headers),
                MAP_TYPE
        );
        Map<String, Object> row = rowsOf(dataOf(list.getBody())).get(0);
        assertThat(row).containsEntry("postName", "测试岗位已更新" + suffix);
        assertThat(row).containsEntry("status", 0);

        ResponseEntity<Map<String, Object>> delete = restTemplate.exchange(
                "/api/system/posts/" + id,
                HttpMethod.DELETE,
                new HttpEntity<>(headers),
                MAP_TYPE
        );
        assertThat(delete.getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<Map<String, Object>> afterDelete = restTemplate.exchange(
                "/api/system/posts?pageNum=1&pageSize=10&keyword=" + suffix,
                HttpMethod.GET,
                new HttpEntity<>(headers),
                MAP_TYPE
        );
        assertThat(rowsOf(dataOf(afterDelete.getBody()))).isEmpty();
    }

    @Test
    void userCrudPersistsAssignmentsAndSoftDeletesRecord() {
        String suffix = uniqueSuffix();
        HttpHeaders headers = bearerHeaders(login("admin", "admin123"));
        Map<String, Object> createBody = Map.of(
                "username", "it_" + suffix,
                "nickname", "集成测试用户" + suffix,
                "password", "admin123",
                        "phone", "",
                "email", "it_" + suffix + "@example.com",
                "deptId", 6,
                "status", 1,
                "roleIds", List.of(4),
                "postIds", List.of(6)
        );

        ResponseEntity<Map<String, Object>> create = restTemplate.exchange(
                "/api/system/users",
                HttpMethod.POST,
                new HttpEntity<>(createBody, headers),
                MAP_TYPE
        );
        assertThat(create.getStatusCode()).isEqualTo(HttpStatus.OK);
        Long id = ((Number) dataOf(create.getBody()).get("id")).longValue();

        ResponseEntity<Map<String, Object>> update = restTemplate.exchange(
                "/api/system/users/" + id,
                HttpMethod.PUT,
                new HttpEntity<>(Map.of("nickname", "集成测试用户已更新" + suffix, "deptId", 7, "status", 0, "roleIds", List.of(5), "postIds", List.of(7)), headers),
                MAP_TYPE
        );
        assertThat(update.getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<Map<String, Object>> list = restTemplate.exchange(
                "/api/system/users?pageNum=1&pageSize=10&keyword=" + suffix,
                HttpMethod.GET,
                new HttpEntity<>(headers),
                MAP_TYPE
        );
        Map<String, Object> row = rowsOf(dataOf(list.getBody())).get(0);
        assertThat(row).containsEntry("nickname", "集成测试用户已更新" + suffix);
        assertThat(row).containsEntry("deptName", "测试质量部");
        assertThat(row).containsEntry("status", 0);

        ResponseEntity<Map<String, Object>> delete = restTemplate.exchange(
                "/api/system/users/" + id,
                HttpMethod.DELETE,
                new HttpEntity<>(headers),
                MAP_TYPE
        );
        assertThat(delete.getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<Map<String, Object>> afterDelete = restTemplate.exchange(
                "/api/system/users?pageNum=1&pageSize=10&keyword=" + suffix,
                HttpMethod.GET,
                new HttpEntity<>(headers),
                MAP_TYPE
        );
        assertThat(rowsOf(dataOf(afterDelete.getBody()))).isEmpty();
    }

    @Test
    void softDeletedUserDoesNotBlockRoleDeletion() {
        String suffix = uniqueSuffix();
        HttpHeaders headers = bearerHeaders(login("admin", "admin123"));

        ResponseEntity<Map<String, Object>> role = restTemplate.exchange(
                "/api/system/roles",
                HttpMethod.POST,
                new HttpEntity<>(Map.of(
                        "name", "软删用户角色" + suffix,
                        "code", "soft_user_role_" + suffix,
                        "dataScope", "SELF",
                        "sort", 99,
                        "status", 1,
                        "menuIds", List.of(101)
                ), headers),
                MAP_TYPE
        );
        assertThat(role.getStatusCode()).isEqualTo(HttpStatus.OK);
        Long roleId = ((Number) dataOf(role.getBody()).get("id")).longValue();

        ResponseEntity<Map<String, Object>> user = restTemplate.exchange(
                "/api/system/users",
                HttpMethod.POST,
                new HttpEntity<>(Map.of(
                        "username", "soft_role_" + suffix,
                        "nickname", "软删角色用户" + suffix,
                        "password", "admin123",
                        "deptId", 6,
                        "status", 1,
                        "roleIds", List.of(roleId),
                        "postIds", List.of(6)
                ), headers),
                MAP_TYPE
        );
        assertThat(user.getStatusCode()).isEqualTo(HttpStatus.OK);
        Long userId = ((Number) dataOf(user.getBody()).get("id")).longValue();

        assertThat(restTemplate.exchange(
                "/api/system/users/" + userId,
                HttpMethod.DELETE,
                new HttpEntity<>(headers),
                MAP_TYPE
        ).getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<Map<String, Object>> deleteRole = restTemplate.exchange(
                "/api/system/roles/" + roleId,
                HttpMethod.DELETE,
                new HttpEntity<>(headers),
                MAP_TYPE
        );
        assertThat(deleteRole.getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void userStatusPasswordAndExportApisWork() {
        String suffix = uniqueSuffix();
        HttpHeaders headers = bearerHeaders(login("admin", "admin123"));
        Long id = createUser(headers, suffix, "it_user_ext_" + suffix, "用户增强测试" + suffix);

        ResponseEntity<Map<String, Object>> disable = restTemplate.exchange(
                "/api/system/users/" + id + "/status",
                HttpMethod.PUT,
                new HttpEntity<>(Map.of("status", 0), headers),
                MAP_TYPE
        );
        assertThat(disable.getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<Map<String, Object>> disabledLogin = TestAuthClient.loginResponse(restTemplate, "it_user_ext_" + suffix, "admin123");
        assertThat(disabledLogin.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(disabledLogin.getBody()).containsEntry("message", "账号已停用");

        ResponseEntity<Map<String, Object>> enable = restTemplate.exchange(
                "/api/system/users/" + id + "/status",
                HttpMethod.PUT,
                new HttpEntity<>(Map.of("status", 1), headers),
                MAP_TYPE
        );
        assertThat(enable.getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<Map<String, Object>> reset = restTemplate.exchange(
                "/api/system/users/" + id + "/password",
                HttpMethod.PUT,
                new HttpEntity<>(Map.of("password", "Yy@123456"), headers),
                MAP_TYPE
        );
        assertThat(reset.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(login("it_user_ext_" + suffix, "Yy@123456")).isNotBlank();

        ResponseEntity<String> export = restTemplate.exchange(
                "/api/system/users/export?keyword=" + suffix,
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );
        assertThat(export.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(export.getHeaders().getContentType()).isEqualTo(MediaType.valueOf("text/csv;charset=UTF-8"));
        assertThat(export.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION)).contains("users");
        assertThat(export.getBody()).contains("登录账号,用户昵称,手机号,邮箱,部门,岗位,角色,状态,创建时间,最近登录");
        assertThat(export.getBody()).contains("it_user_ext_" + suffix);

        restTemplate.exchange(
                "/api/system/users/" + id,
                HttpMethod.DELETE,
                new HttpEntity<>(headers),
                MAP_TYPE
        );
    }

    private Long createUser(HttpHeaders headers, String suffix, String username, String nickname) {
        Map<String, Object> createBody = Map.of(
                "username", username,
                "nickname", nickname,
                "password", "admin123",
                "phone", "",
                "email", username + "@example.com",
                "deptId", 6,
                "status", 1,
                "roleIds", List.of(4),
                "postIds", List.of(6)
        );
        ResponseEntity<Map<String, Object>> create = restTemplate.exchange(
                "/api/system/users",
                HttpMethod.POST,
                new HttpEntity<>(createBody, headers),
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

    private String uniqueSuffix() {
        return String.valueOf(System.nanoTime());
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
