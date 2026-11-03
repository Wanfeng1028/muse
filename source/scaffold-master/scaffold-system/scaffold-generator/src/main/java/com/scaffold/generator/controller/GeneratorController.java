package com.scaffold.generator.controller;

import com.scaffold.common.domain.PageQuery;
import com.scaffold.common.domain.PageResult;
import com.scaffold.common.domain.R;
import com.scaffold.framework.audit.OperLog;
import com.scaffold.framework.security.RequiresPermission;
import com.scaffold.generator.service.GeneratorService;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/tool/generator")
public class GeneratorController {

    private final GeneratorService service;

    public GeneratorController(GeneratorService service) {
        this.service = service;
    }

    @GetMapping("/tables")
    @RequiresPermission("tool:gen:list")
    public R<PageResult<Map<String, Object>>> tables(PageQuery query, @RequestParam(required = false) String keyword) {
        return R.success(service.tables(query, keyword));
    }

    @GetMapping("/importable-tables")
    @RequiresPermission("tool:gen:list")
    public R<List<Map<String, Object>>> importableTables(@RequestParam(required = false) String keyword) {
        return R.success(service.importableTables(keyword));
    }

    @PostMapping("/import")
    @RequiresPermission("tool:gen:list")
    @OperLog(module = "代码生成", action = "导入表")
    @SuppressWarnings("unchecked")
    public R<Map<String, Object>> importTables(@RequestBody Map<String, Object> request) {
        return R.success(service.importTables((List<String>) request.get("tableNames")));
    }

    @GetMapping("/tables/{id}/columns")
    @RequiresPermission("tool:gen:list")
    public R<List<Map<String, Object>>> columns(@PathVariable Long id) {
        return R.success(service.columns(id));
    }

    @GetMapping("/tables/{id}/preview")
    @RequiresPermission("tool:gen:list")
    public R<Map<String, Object>> preview(@PathVariable Long id) {
        return R.success(service.preview(id));
    }

    @PutMapping("/tables/{id}")
    @RequiresPermission("tool:gen:list")
    @OperLog(module = "代码生成", action = "修改配置")
    public R<Void> update(@PathVariable Long id, @RequestBody Map<String, Object> request) {
        service.updateTable(id, request);
        return R.success(null);
    }

    @PostMapping("/tables/{id}/generate")
    @RequiresPermission("tool:gen:list")
    @OperLog(module = "代码生成", action = "生成代码")
    public R<Map<String, Object>> generate(@PathVariable Long id) {
        return R.success(service.generate(id));
    }

    @GetMapping("/tables/{id}/download")
    @RequiresPermission("tool:gen:list")
    @OperLog(module = "代码生成", action = "下载代码")
    public ResponseEntity<byte[]> download(@PathVariable Long id) {
        Map<String, Object> preview = service.preview(id);
        String activeFile = String.valueOf(preview.get("activeFile"));
        String className = activeFile.endsWith("Controller.java")
                ? activeFile.substring(0, activeFile.length() - "Controller.java".length())
                : "code";
        return ResponseEntity.ok()
                .contentType(MediaType.valueOf("application/zip"))
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + className + ".zip\"")
                .body(service.download(id));
    }
}
