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
class SystemCatalogWriteApiTest {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_TYPE = new ParameterizedTypeReference<>() {
    };

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void roleCrudPersistsAndSoftDeletesRecord() {
        String suffix = uniqueSuffix();
        HttpHeaders headers = bearerHeaders(login());

        ResponseEntity<Map<String, Object>> create = exchange("/api/system/roles", HttpMethod.POST, Map.of(
                "name", "集成测试角色" + suffix,
                "code", "it_role_" + suffix,
                "dataScope", "SELF",
                "sort", 88,
                "status", 1,
                "remark", "集成测试创建"
        ), headers);
        assertThat(create.getStatusCode()).isEqualTo(HttpStatus.OK);
        Long id = idOf(create.getBody());

        ResponseEntity<Map<String, Object>> update = exchange("/api/system/roles/" + id, HttpMethod.PUT, Map.of(
                "name", "集成测试角色已更新" + suffix,
                "dataScope", "CUSTOM",
                "sort", 89,
                "status", 0,
                "remark", "已更新"
        ), headers);
        assertThat(update.getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<Map<String, Object>> list = exchange("/api/system/roles?pageNum=1&pageSize=10&keyword=" + suffix, HttpMethod.GET, null, headers);
        Map<String, Object> role = rowsOf(dataOf(list.getBody())).get(0);
        assertThat(role).containsEntry("name", "集成测试角色已更新" + suffix);
        assertThat(role).containsEntry("dataScope", "自定义数据权限");

        assertThat(exchange("/api/system/roles/" + id, HttpMethod.DELETE, null, headers).getStatusCode()).isEqualTo(HttpStatus.OK);
        ResponseEntity<Map<String, Object>> afterDelete = exchange("/api/system/roles?pageNum=1&pageSize=10&keyword=" + suffix, HttpMethod.GET, null, headers);
        assertThat(rowsOf(dataOf(afterDelete.getBody()))).isEmpty();
    }

    @Test
    void deptAndMenuCrudPersistAndDeleteRecords() {
        String suffix = uniqueSuffix();
        HttpHeaders headers = bearerHeaders(login());

        ResponseEntity<Map<String, Object>> deptCreate = exchange("/api/system/depts", HttpMethod.POST, Map.of(
                "parentId", 1,
                "name", "集成测试部门" + suffix,
                "leader", "测试负责人",
                        "phone", "",
                "email", "dept_" + suffix + "@example.com",
                "sort", 90,
                "status", 1
        ), headers);
        assertThat(deptCreate.getStatusCode()).isEqualTo(HttpStatus.OK);
        Long deptId = idOf(deptCreate.getBody());

        ResponseEntity<Map<String, Object>> deptUpdate = exchange("/api/system/depts/" + deptId, HttpMethod.PUT, Map.of(
                "name", "集成测试部门已更新" + suffix,
                "leader", "新负责人",
                "status", 0
        ), headers);
        assertThat(deptUpdate.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(exchange("/api/system/depts/" + deptId, HttpMethod.DELETE, null, headers).getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<Map<String, Object>> menuCreate = exchange("/api/system/menus", HttpMethod.POST, Map.of(
                "parentId", 100,
                "name", "集成测试菜单" + suffix,
                "type", "menu",
                "icon", "menu",
                "path", "/system/it-" + suffix,
                "component", "system/it/index",
                "permission", "system:it:list:" + suffix,
                "sort", 90,
                "visible", 1,
                "status", 1
        ), headers);
        assertThat(menuCreate.getStatusCode()).isEqualTo(HttpStatus.OK);
        Long menuId = idOf(menuCreate.getBody());

        ResponseEntity<Map<String, Object>> menuUpdate = exchange("/api/system/menus/" + menuId, HttpMethod.PUT, Map.of(
                "name", "集成测试菜单已更新" + suffix,
                "visible", 0,
                "status", 0
        ), headers);
        assertThat(menuUpdate.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(exchange("/api/system/menus/" + menuId, HttpMethod.DELETE, null, headers).getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void dictionaryAndConfigCrudPersistAndDeleteRecords() {
        String suffix = uniqueSuffix();
        HttpHeaders headers = bearerHeaders(login());
        String dictType = "it_dict_" + suffix;

        ResponseEntity<Map<String, Object>> dictTypeCreate = exchange("/api/system/dict/types", HttpMethod.POST, Map.of(
                "dictName", "集成测试字典" + suffix,
                "dictType", dictType,
                "status", 1,
                "remark", "集成测试创建"
        ), headers);
        assertThat(dictTypeCreate.getStatusCode()).isEqualTo(HttpStatus.OK);
        Long dictTypeId = idOf(dictTypeCreate.getBody());

        ResponseEntity<Map<String, Object>> dictDataCreate = exchange("/api/system/dict/data", HttpMethod.POST, Map.of(
                "dictType", dictType,
                "label", "选项A",
                "value", "A",
                "sort", 1,
                "status", 1,
                "tone", "ok",
                "def", true
        ), headers);
        assertThat(dictDataCreate.getStatusCode()).isEqualTo(HttpStatus.OK);
        Long dictDataId = idOf(dictDataCreate.getBody());

        ResponseEntity<Map<String, Object>> dictData = exchange("/api/system/dict/data/" + dictType, HttpMethod.GET, null, headers);
        assertThat(listDataOf(dictData.getBody())).extracting(row -> row.get("label")).contains("选项A");

        assertThat(exchange("/api/system/dict/data/" + dictDataId, HttpMethod.DELETE, null, headers).getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(exchange("/api/system/dict/types/" + dictTypeId, HttpMethod.DELETE, null, headers).getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<Map<String, Object>> configCreate = exchange("/api/system/configs", HttpMethod.POST, Map.of(
                "name", "集成测试参数" + suffix,
                "key", "it.config." + suffix,
                "value", "enabled",
                "type", "N",
                "builtin", false,
                "remark", "集成测试创建"
        ), headers);
        assertThat(configCreate.getStatusCode()).isEqualTo(HttpStatus.OK);
        Long configId = idOf(configCreate.getBody());

        ResponseEntity<Map<String, Object>> configUpdate = exchange("/api/system/configs/" + configId, HttpMethod.PUT, Map.of(
                "name", "集成测试参数已更新" + suffix,
                "value", "disabled",
                "remark", "已更新"
        ), headers);
        assertThat(configUpdate.getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<Map<String, Object>> configs = exchange("/api/system/configs?pageNum=1&pageSize=10&keyword=" + suffix, HttpMethod.GET, null, headers);
        Map<String, Object> config = rowsOf(dataOf(configs.getBody())).get(0);
        assertThat(config).containsEntry("name", "集成测试参数已更新" + suffix);
        assertThat(config).containsEntry("value", "disabled");

        assertThat(exchange("/api/system/configs/" + configId, HttpMethod.DELETE, null, headers).getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    private ResponseEntity<Map<String, Object>> exchange(String path, HttpMethod method, Object body, HttpHeaders headers) {
        return restTemplate.exchange(path, method, new HttpEntity<>(body, headers), MAP_TYPE);
    }

    private String login() {
        return TestAuthClient.login(restTemplate, "admin", "admin123");
    }

    private HttpHeaders bearerHeaders(String token) {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(token);
        return headers;
    }

    private Long idOf(Map<String, Object> body) {
        return ((Number) dataOf(body).get("id")).longValue();
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
    private List<Map<String, Object>> listDataOf(Map<String, Object> body) {
        assertThat(body).containsEntry("code", 200);
        return (List<Map<String, Object>>) body.get("data");
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> rowsOf(Map<String, Object> page) {
        return (List<Map<String, Object>>) page.get("rows");
    }
}
