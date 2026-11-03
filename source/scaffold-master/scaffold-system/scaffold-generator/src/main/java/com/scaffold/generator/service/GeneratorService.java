package com.scaffold.generator.service;

import com.scaffold.common.domain.PageQuery;
import com.scaffold.common.domain.PageResult;
import com.scaffold.common.exception.BusinessException;
import com.scaffold.generator.mapper.GeneratorMapper;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

@Service
public class GeneratorService {

    private final GeneratorMapper mapper;

    public GeneratorService(GeneratorMapper mapper) {
        this.mapper = mapper;
    }

    public PageResult<Map<String, Object>> tables(PageQuery query, String keyword) {
        Page page = pageOf(query);
        return PageResult.of(booleanRows(mapper.selectTables(keyword, page.offset(), page.pageSize()), "synced"),
                mapper.countTables(keyword), page.pageNum(), page.pageSize());
    }

    public List<Map<String, Object>> columns(Long tableId) {
        ensureTable(tableId);
        return booleanRows(mapper.selectColumns(tableId), "insert", "edit", "list", "query", "required");
    }

    public List<Map<String, Object>> importableTables(String keyword) {
        return booleanRows(mapper.selectImportableTables(keyword), "imported");
    }

    @Transactional
    public Map<String, Object> importTables(List<String> tableNames) {
        if (tableNames == null || tableNames.isEmpty()) {
            throw new BusinessException("请选择要导入的数据库表");
        }
        List<Long> ids = new ArrayList<>();
        for (String tableName : tableNames) {
            Long existingId = mapper.selectTableIdByName(tableName);
            if (existingId != null) {
                ids.add(existingId);
                continue;
            }
            Map<String, Object> dbTable = mapper.selectDatabaseTable(tableName);
            if (dbTable == null) {
                throw new BusinessException("数据库表不存在：" + tableName);
            }
            Map<String, Object> row = tableRow(dbTable);
            mapper.insertTable(row, currentUsername());
            Long tableId = numberAsLong(row.get("id"));
            for (Map<String, Object> column : mapper.selectDatabaseColumns(tableName)) {
                mapper.insertColumn(columnRow(tableId, column));
            }
            ids.add(tableId);
        }
        return Map.of("imported", ids.size(), "ids", ids);
    }

    public Map<String, Object> preview(Long tableId) {
        Map<String, Object> table = ensureTable(tableId);
        String className = String.valueOf(table.get("className"));
        String activeFile = className + "Controller.java";
        List<Map<String, Object>> files = new ArrayList<>();
        String activeCode = "";
        for (Map.Entry<String, String> entry : renderFiles(table, mapper.selectColumns(tableId)).entrySet()) {
            String path = entry.getKey();
            String name = path.substring(path.lastIndexOf('/') + 1);
            Map<String, Object> file = new LinkedHashMap<>();
            file.put("name", name);
            file.put("path", path);
            file.put("code", entry.getValue());
            files.add(file);
            if (name.equals(activeFile)) activeCode = entry.getValue();
        }
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("files", files);
        data.put("activeFile", activeFile);
        data.put("code", activeCode);
        return data;
    }

    @Transactional
    public void updateTable(Long id, Map<String, Object> request) {
        String tableComment = request == null ? null : asString(request.get("tableComment"));
        Integer synced = null;
        if (request != null && request.containsKey("synced")) {
            synced = Boolean.TRUE.equals(request.get("synced")) ? 1 : 0;
        }
        if (mapper.updateTable(id, tableComment, synced, currentUsername()) == 0) {
            throw new BusinessException("代码生成表不存在");
        }
    }

    public Map<String, Object> generate(Long tableId) {
        Map<String, Object> table = ensureTable(tableId);
        return Map.of(
                "tableName", table.get("tableName"),
                "message", "代码压缩包已准备就绪"
        );
    }

    public byte[] download(Long tableId) {
        Map<String, Object> table = ensureTable(tableId);
        List<Map<String, Object>> columns = mapper.selectColumns(tableId);
        Map<String, String> files = renderFiles(table, columns);
        try {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            try (ZipOutputStream zip = new ZipOutputStream(out, StandardCharsets.UTF_8)) {
                for (Map.Entry<String, String> file : files.entrySet()) {
                    zip.putNextEntry(new ZipEntry(file.getKey()));
                    zip.write(file.getValue().getBytes(StandardCharsets.UTF_8));
                    zip.closeEntry();
                }
            }
            return out.toByteArray();
        } catch (IOException error) {
            throw new BusinessException("代码压缩包生成失败");
        }
    }

    private Map<String, Object> ensureTable(Long tableId) {
        Map<String, Object> table = mapper.selectTableById(tableId);
        if (table == null) {
            throw new BusinessException("代码生成表不存在");
        }
        return table;
    }

    private Map<String, Object> tableRow(Map<String, Object> dbTable) {
        String tableName = String.valueOf(dbTable.get("tableName"));
        String businessName = businessName(tableName);
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("tableName", tableName);
        row.put("tableComment", dbTable.get("tableComment"));
        row.put("className", upperCamel(tableName));
        row.put("module", moduleName(tableName));
        row.put("businessName", businessName);
        return row;
    }

    private Map<String, Object> columnRow(Long tableId, Map<String, Object> column) {
        String columnName = String.valueOf(column.get("columnName"));
        String dataType = String.valueOf(column.get("dataType")).toLowerCase(Locale.ROOT);
        boolean primaryLike = "id".equals(columnName);
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("tableId", tableId);
        row.put("columnName", columnName);
        row.put("javaField", lowerCamel(columnName));
        row.put("javaType", javaType(dataType));
        row.put("jdbcType", dataType);
        row.put("columnComment", column.get("columnComment"));
        row.put("insert", primaryLike ? 0 : 1);
        row.put("edit", primaryLike ? 0 : 1);
        row.put("list", primaryLike ? 0 : 1);
        row.put("query", queryField(columnName) ? 1 : 0);
        row.put("queryType", queryField(columnName) ? "LIKE" : "=");
        row.put("formType", formType(dataType));
        row.put("required", "NO".equals(column.get("nullable")) && !primaryLike ? 1 : 0);
        row.put("sort", column.get("sort"));
        return row;
    }

    private Map<String, String> renderFiles(Map<String, Object> table, List<Map<String, Object>> columns) {
        String tableName = String.valueOf(table.get("tableName"));
        String className = String.valueOf(table.get("className"));
        String module = String.valueOf(table.get("module"));
        String resource = decapitalize(className);
        Map<String, String> files = new LinkedHashMap<>();
        files.put("backend/src/main/java/com/scaffold/%s/domain/%s.java".formatted(module, className), entityCode(module, className, columns));
        files.put("backend/src/main/java/com/scaffold/%s/mapper/%sMapper.java".formatted(module, className), mapperCode(module, className));
        files.put("backend/src/main/java/com/scaffold/%s/service/%sService.java".formatted(module, className), serviceCode(module, className));
        files.put("backend/src/main/java/com/scaffold/%s/controller/%sController.java".formatted(module, className), controllerCode(module, className, resource));
        files.put("frontend/src/api/%s/%s.ts".formatted(module, resource), apiCode(module, resource));
        files.put("frontend/src/views/%s/%s/index.vue".formatted(module, resource), viewCode(tableName, className, columns));
        files.put("sql/%s_menu.sql".formatted(tableName), menuSql(tableName, className, module, resource));
        return files;
    }

    private String entityCode(String module, String className, List<Map<String, Object>> columns) {
        StringBuilder fields = new StringBuilder();
        boolean needsBigDecimal = false;
        boolean needsLocalDateTime = false;
        for (Map<String, Object> column : columns) {
            String javaType = String.valueOf(column.get("javaType"));
            needsBigDecimal = needsBigDecimal || "BigDecimal".equals(javaType);
            needsLocalDateTime = needsLocalDateTime || "LocalDateTime".equals(javaType);
            fields.append("    /** ").append(nullAsEmpty(column.get("comment"))).append(" */\n")
                    .append("    private ").append(javaType).append(" ").append(column.get("javaField")).append(";\n\n");
        }
        String imports = "";
        if (needsBigDecimal) {
            imports += "import java.math.BigDecimal;\n";
        }
        if (needsLocalDateTime) {
            imports += "import java.time.LocalDateTime;\n";
        }
        if (!imports.isBlank()) {
            imports += "\n";
        }
        return """
                package com.scaffold.%s.domain;

                %s
                public class %s {
                %s}
                """.formatted(module, imports, className, fields);
    }

    private String mapperCode(String module, String className) {
        return """
                package com.scaffold.%s.mapper;

                import org.apache.ibatis.annotations.Mapper;

                @Mapper
                public interface %sMapper {
                }
                """.formatted(module, className);
    }

    private String serviceCode(String module, String className) {
        return """
                package com.scaffold.%s.service;

                import org.springframework.stereotype.Service;

                @Service
                public class %sService {
                }
                """.formatted(module, className);
    }

    private String controllerCode(String module, String className, String resource) {
        return """
                package com.scaffold.%s.controller;

                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/api/%s/%s")
                public class %sController {
                }
                """.formatted(module, module, resource, className);
    }

    private String apiCode(String module, String resource) {
        return """
                import { httpClient } from '@/api/http'

                export const %sApi = {
                  list: (query?: Record<string, unknown>) => httpClient.get('/%s/%s', query as any),
                }
                """.formatted(resource, module, resource);
    }

    private String viewCode(String tableName, String className, List<Map<String, Object>> columns) {
        String firstListField = columns.stream()
                .filter(column -> enabled(column.get("list")))
                .map(column -> String.valueOf(column.get("javaField")))
                .findFirst()
                .orElse("id");
        return """
                <script setup lang="ts">
                const tableName = '%s'
                const className = '%s'
                const primaryField = '%s'
                </script>

                <template>
                  <div>
                    <h1>{{ className }}</h1>
                    <p>{{ tableName }} · {{ primaryField }}</p>
                  </div>
                </template>
                """.formatted(tableName, className, firstListField);
    }

    private String menuSql(String tableName, String className, String module, String resource) {
        return """
                -- %s 菜单权限
                INSERT INTO sys_menu (id, parent_id, menu_name, menu_type, path, component, permission, sort, visible, status, create_by, update_by)
                SELECT COALESCE(MAX(id), 0) + 1, 0, '%s管理', 'menu', '/%s/%s', '%s/%s/index', '%s:%s:list', 1, 1, 1, 'system', 'system'
                FROM sys_menu;
                """.formatted(tableName, className, module, resource, module, resource, module, resource);
    }

    private boolean enabled(Object value) {
        if (value instanceof Number number) {
            return number.intValue() == 1;
        }
        return Boolean.TRUE.equals(value);
    }

    private String nullAsEmpty(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private List<Map<String, Object>> booleanRows(List<Map<String, Object>> rows, String... keys) {
        for (Map<String, Object> row : rows) {
            for (String key : keys) {
                Object value = row.get(key);
                if (value instanceof Number number) {
                    row.put(key, number.intValue() == 1);
                }
            }
        }
        return rows;
    }

    private Page pageOf(PageQuery query) {
        int pageNum = query == null ? PageQuery.DEFAULT_PAGE_NUM : query.normalizedPageNum();
        int pageSize = query == null ? PageQuery.DEFAULT_PAGE_SIZE : query.normalizedPageSize();
        return new Page(pageNum, pageSize);
    }

    private String currentUsername() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        return authentication == null ? "system" : String.valueOf(authentication.getPrincipal());
    }

    private String asString(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private String decapitalize(String value) {
        if (value == null || value.isBlank()) {
            return value;
        }
        return Character.toLowerCase(value.charAt(0)) + value.substring(1);
    }

    private String moduleName(String tableName) {
        int split = tableName.indexOf('_');
        String module = split > 0 ? tableName.substring(0, split) : "system";
        return "sys".equals(module) ? "system" : module;
    }

    private String businessName(String tableName) {
        int split = tableName.indexOf('_');
        String raw = split > 0 ? tableName.substring(split + 1) : tableName;
        return lowerCamel(raw);
    }

    private String upperCamel(String value) {
        String lower = lowerCamel(value);
        return lower == null || lower.isBlank() ? lower : Character.toUpperCase(lower.charAt(0)) + lower.substring(1);
    }

    private String lowerCamel(String value) {
        if (value == null || value.isBlank()) {
            return value;
        }
        StringBuilder builder = new StringBuilder();
        for (String part : value.toLowerCase(Locale.ROOT).split("_")) {
            if (part.isBlank()) {
                continue;
            }
            if (builder.isEmpty()) {
                builder.append(part);
            } else {
                builder.append(Character.toUpperCase(part.charAt(0))).append(part.substring(1));
            }
        }
        return builder.toString();
    }

    private String javaType(String dataType) {
        return switch (dataType) {
            case "bigint" -> "Long";
            case "int", "integer", "smallint", "tinyint" -> "Integer";
            case "decimal", "numeric" -> "BigDecimal";
            case "datetime", "timestamp", "date", "time" -> "LocalDateTime";
            default -> "String";
        };
    }

    private String formType(String dataType) {
        return switch (dataType) {
            case "text", "longtext", "mediumtext" -> "文本域";
            case "int", "integer", "smallint", "tinyint", "bigint", "decimal", "numeric" -> "数字框";
            case "datetime", "timestamp", "date", "time" -> "日期框";
            default -> "文本框";
        };
    }

    private boolean queryField(String columnName) {
        String lower = columnName.toLowerCase(Locale.ROOT);
        return lower.contains("name") || lower.contains("code") || lower.contains("status") || lower.contains("type");
    }

    private Long numberAsLong(Object value) {
        return value instanceof Number number ? number.longValue() : Long.valueOf(String.valueOf(value));
    }

    private record Page(int pageNum, int pageSize) {
        int offset() {
            return (pageNum - 1) * pageSize;
        }
    }
}
