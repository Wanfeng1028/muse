package com.scaffold.admin;

import org.junit.jupiter.api.BeforeEach;
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
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ScaffoldAdminApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class GeneratorImportApiTest {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_TYPE = new ParameterizedTypeReference<>() {
    };

    @Autowired
    private TestRestTemplate restTemplate;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @BeforeEach
    void cleanImportedTable() {
        List<Long> ids = jdbcTemplate.queryForList("SELECT id FROM gen_table WHERE table_name = 'sys_file'", Long.class);
        for (Long tableId : ids) {
            jdbcTemplate.update("DELETE FROM gen_table_column WHERE table_id = ?", tableId);
            jdbcTemplate.update("DELETE FROM gen_table WHERE id = ?", tableId);
        }
    }

    @Test
    void generatorCanListAndImportDatabaseTables() {
        HttpHeaders headers = bearerHeaders(login("admin", "admin123"));

        ResponseEntity<Map<String, Object>> candidates = restTemplate.exchange(
                "/api/tool/generator/importable-tables?keyword=sys_file",
                HttpMethod.GET,
                new HttpEntity<>(null, headers),
                MAP_TYPE
        );
        assertThat(candidates.getStatusCode()).isEqualTo(HttpStatus.OK);
        Map<String, Object> candidate = listDataOf(candidates.getBody()).get(0);
        assertThat(candidate).containsEntry("tableName", "sys_file");
        assertThat(candidate).containsEntry("tableComment", "文件信息表");
        assertThat(candidate).containsEntry("imported", false);

        ResponseEntity<Map<String, Object>> imported = restTemplate.exchange(
                "/api/tool/generator/import",
                HttpMethod.POST,
                new HttpEntity<>(Map.of("tableNames", List.of("sys_file")), headers),
                MAP_TYPE
        );
        assertThat(imported.getStatusCode()).isEqualTo(HttpStatus.OK);
        Map<String, Object> importData = dataOf(imported.getBody());
        assertThat(((Number) importData.get("imported")).intValue()).isEqualTo(1);

        Long tableId = jdbcTemplate.queryForObject("SELECT id FROM gen_table WHERE table_name = 'sys_file'", Long.class);
        assertThat(tableId).isNotNull();
        assertThat(jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM gen_table_column WHERE table_id = ? AND column_name = 'original_name'",
                Long.class,
                tableId
        )).isEqualTo(1);
    }

    @Test
    void generatorCanDownloadCodeZip() throws IOException {
        HttpHeaders headers = bearerHeaders(login("admin", "admin123"));
        ResponseEntity<Map<String, Object>> imported = restTemplate.exchange(
                "/api/tool/generator/import",
                HttpMethod.POST,
                new HttpEntity<>(Map.of("tableNames", List.of("sys_file")), headers),
                MAP_TYPE
        );
        assertThat(imported.getStatusCode()).isEqualTo(HttpStatus.OK);
        Long tableId = jdbcTemplate.queryForObject("SELECT id FROM gen_table WHERE table_name = 'sys_file'", Long.class);

        ResponseEntity<byte[]> download = restTemplate.exchange(
                "/api/tool/generator/tables/" + tableId + "/download",
                HttpMethod.GET,
                new HttpEntity<>(null, headers),
                byte[].class
        );

        assertThat(download.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(download.getHeaders().getContentType()).isEqualTo(MediaType.valueOf("application/zip"));
        assertThat(download.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION)).contains("SysFile.zip");

        Map<String, String> files = unzip(download.getBody());
        assertThat(files).containsKeys(
                "backend/src/main/java/com/scaffold/system/domain/SysFile.java",
                "backend/src/main/java/com/scaffold/system/mapper/SysFileMapper.java",
                "backend/src/main/java/com/scaffold/system/service/SysFileService.java",
                "backend/src/main/java/com/scaffold/system/controller/SysFileController.java",
                "frontend/src/api/system/sysFile.ts",
                "frontend/src/views/system/sysFile/index.vue",
                "sql/sys_file_menu.sql"
        );
        assertThat(files.get("backend/src/main/java/com/scaffold/system/controller/SysFileController.java"))
                .contains("class SysFileController")
                .contains("@RequestMapping(\"/api/system/sysFile\")");
        assertThat(files.get("frontend/src/views/system/sysFile/index.vue"))
                .contains("SysFile")
                .contains("sys_file");
        assertThat(files.get("sql/sys_file_menu.sql")).contains("sys_file");
        Long menuCount = jdbcTemplate.queryForObject("SELECT COUNT(*) FROM sys_menu", Long.class);
        new TransactionTemplate(transactionManager).executeWithoutResult(status -> {
            jdbcTemplate.execute(files.get("sql/sys_file_menu.sql"));
            assertThat(jdbcTemplate.queryForObject("SELECT COUNT(*) FROM sys_menu", Long.class)).isEqualTo(menuCount + 1);
            assertThat(jdbcTemplate.queryForMap("SELECT menu_type, permission FROM sys_menu WHERE id = (SELECT MAX(id) FROM sys_menu)"))
                    .containsEntry("menu_type", "menu")
                    .containsEntry("permission", "system:sysFile:list");
            status.setRollbackOnly();
        });
        assertThat(jdbcTemplate.queryForObject("SELECT COUNT(*) FROM sys_menu", Long.class)).isEqualTo(menuCount);
    }

    private String login(String username, String password) {
        return TestAuthClient.login(restTemplate, username, password);
    }

    private HttpHeaders bearerHeaders(String token) {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(token);
        return headers;
    }

    private Map<String, String> unzip(byte[] body) throws IOException {
        java.util.LinkedHashMap<String, String> files = new java.util.LinkedHashMap<>();
        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(body))) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                files.put(entry.getName(), new String(zip.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8));
            }
        }
        return files;
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
}
