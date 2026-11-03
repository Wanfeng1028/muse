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

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ScaffoldAdminApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class SystemReadApiTest {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_TYPE = new ParameterizedTypeReference<>() {
    };

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void userAndRoleListsReturnFrontendFields() {
        HttpEntity<Void> entity = authorizedEntity();

        ResponseEntity<Map<String, Object>> users = restTemplate.exchange(
                "/api/system/users?pageNum=1&pageSize=5&keyword=admin",
                HttpMethod.GET,
                entity,
                MAP_TYPE
        );
        assertThat(users.getStatusCode()).isEqualTo(HttpStatus.OK);
        Map<String, Object> userPage = dataOf(users.getBody());
        assertThat(((Number) userPage.get("total")).longValue()).isGreaterThanOrEqualTo(1);
        Map<String, Object> user = rowsOf(userPage).get(0);
        assertThat(user).containsEntry("username", "admin");
        assertThat(user).containsKeys("nickname", "deptName", "postName", "roleName", "lastLogin");

        ResponseEntity<Map<String, Object>> roles = restTemplate.exchange(
                "/api/system/roles?pageNum=1&pageSize=10&keyword=admin",
                HttpMethod.GET,
                entity,
                MAP_TYPE
        );
        assertThat(roles.getStatusCode()).isEqualTo(HttpStatus.OK);
        Map<String, Object> role = rowsOf(dataOf(roles.getBody())).get(0);
        assertThat(role).containsEntry("code", "super_admin");
        assertThat(role).containsEntry("builtin", true);
        assertThat(((Number) role.get("userCount")).longValue()).isGreaterThanOrEqualTo(1);
    }

    @Test
    void usersListFiltersByPostId() {
        // 种子数据 sys_user_post 仅 (1,3),(2,5),(3,6)：岗位 3 下只有 admin
        ResponseEntity<Map<String, Object>> response = restTemplate.exchange(
                "/api/system/users?pageNum=1&pageSize=10&postId=3",
                HttpMethod.GET,
                authorizedEntity(),
                MAP_TYPE
        );
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        Map<String, Object> page = dataOf(response.getBody());
        assertThat(((Number) page.get("total")).longValue()).isEqualTo(1);
        assertThat(rowsOf(page).get(0)).containsEntry("username", "admin");
    }

    @Test
    @SuppressWarnings("unchecked")
    void permissionGraphReturnsRolesMenusAndUserRoleLinks() {
        ResponseEntity<Map<String, Object>> response = restTemplate.exchange(
                "/api/system/permissions/graph",
                HttpMethod.GET,
                authorizedEntity(),
                MAP_TYPE
        );
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        Map<String, Object> graph = dataOf(response.getBody());
        assertThat(graph).containsEntry("usersVisible", true);
        List<Map<String, Object>> roles = (List<Map<String, Object>>) graph.get("roles");
        assertThat(roles).extracting(row -> row.get("code")).contains("super_admin");
        assertThat(roles.get(0)).containsKeys("id", "name", "dataScope", "builtin", "userCount", "menuIds");
        List<Map<String, Object>> menus = (List<Map<String, Object>>) graph.get("menus");
        assertThat(menus).extracting(row -> row.get("permission")).contains("system:user:remove");
        List<Map<String, Object>> users = (List<Map<String, Object>>) graph.get("users");
        assertThat(users).extracting(row -> row.get("username")).contains("admin");
        assertThat(users.get(0)).doesNotContainKeys("password", "phone", "email");
        List<List<Number>> links = (List<List<Number>>) graph.get("userRoles");
        assertThat(links).anySatisfy(link -> assertThat(link).hasSize(2));
    }

    @Test
    void permissionGraphRequiresLogin() {
        ResponseEntity<Map<String, Object>> response = restTemplate.exchange(
                "/api/system/permissions/graph",
                HttpMethod.GET,
                HttpEntity.EMPTY,
                MAP_TYPE
        );
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void menuAndDeptApisReturnTreeStructures() {
        HttpEntity<Void> entity = authorizedEntity();

        ResponseEntity<Map<String, Object>> menus = restTemplate.exchange(
                "/api/system/menus/tree",
                HttpMethod.GET,
                entity,
                MAP_TYPE
        );
        assertThat(menus.getStatusCode()).isEqualTo(HttpStatus.OK);
        List<Map<String, Object>> menuTree = listDataOf(menus.getBody());
        assertThat(menuTree).extracting(row -> row.get("path")).contains("/dashboard", "/system");
        Map<String, Object> systemMenu = menuTree.stream()
                .filter(row -> "/system".equals(row.get("path")))
                .findFirst()
                .orElseThrow();
        assertThat(childrenOf(systemMenu)).extracting(row -> row.get("path")).contains("/system/user", "/system/role");

        ResponseEntity<Map<String, Object>> depts = restTemplate.exchange(
                "/api/system/depts/tree",
                HttpMethod.GET,
                entity,
                MAP_TYPE
        );
        assertThat(depts.getStatusCode()).isEqualTo(HttpStatus.OK);
        List<Map<String, Object>> deptTree = listDataOf(depts.getBody());
        assertThat(deptTree).extracting(row -> row.get("name")).contains("云原科技集团");
        assertThat(childrenOf(deptTree.get(0))).extracting(row -> row.get("name")).contains("研发中心", "产品中心");
    }

    @Test
    void dictionaryConfigAndLogApisReturnData() {
        HttpEntity<Void> entity = authorizedEntity();

        ResponseEntity<Map<String, Object>> dictTypes = restTemplate.exchange(
                "/api/system/dict/types?pageNum=1&pageSize=20",
                HttpMethod.GET,
                entity,
                MAP_TYPE
        );
        assertThat(dictTypes.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(rowsOf(dataOf(dictTypes.getBody()))).extracting(row -> row.get("dictType")).contains("sys_user_sex");

        ResponseEntity<Map<String, Object>> dictData = restTemplate.exchange(
                "/api/system/dict/data/sys_user_sex",
                HttpMethod.GET,
                entity,
                MAP_TYPE
        );
        assertThat(dictData.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(listDataOf(dictData.getBody())).extracting(row -> row.get("label")).contains("男", "女");

        ResponseEntity<Map<String, Object>> configs = restTemplate.exchange(
                "/api/system/configs?pageNum=1&pageSize=20",
                HttpMethod.GET,
                entity,
                MAP_TYPE
        );
        assertThat(configs.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(rowsOf(dataOf(configs.getBody()))).extracting(row -> row.get("key")).contains("sys.user.initPassword");

        ResponseEntity<Map<String, Object>> loginLogs = restTemplate.exchange(
                "/api/monitor/login-logs?pageNum=1&pageSize=5&keyword=admin",
                HttpMethod.GET,
                entity,
                MAP_TYPE
        );
        assertThat(loginLogs.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(((Number) dataOf(loginLogs.getBody()).get("total")).longValue()).isGreaterThanOrEqualTo(1);
    }

    private HttpEntity<Void> authorizedEntity() {
        String token = loginAsAdmin();
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(token);
        return new HttpEntity<>(headers);
    }

    private String loginAsAdmin() {
        return TestAuthClient.login(restTemplate, "admin", "admin123");
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> dataOf(Map<String, Object> body) {
        assertThat(body).containsEntry("code", 200);
        return (Map<String, Object>) body.get("data");
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> listDataOf(Map<String, Object> body) {
        assertThat(body).containsEntry("code", 200);
        return (List<Map<String, Object>>) body.get("data");
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> rowsOf(Map<String, Object> page) {
        return (List<Map<String, Object>>) page.get("rows");
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> childrenOf(Map<String, Object> row) {
        return (List<Map<String, Object>>) row.get("children");
    }
}
