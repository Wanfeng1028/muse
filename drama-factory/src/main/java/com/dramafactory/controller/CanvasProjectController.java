package com.dramafactory.controller;

import com.dramafactory.service.CanvasProjectService;
import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@Tag(name = "Canvas", description = "编排画布项目 JSON 的读写接口")
public class CanvasProjectController {

    private final CanvasProjectService canvasProjectService;

    public CanvasProjectController(CanvasProjectService canvasProjectService) {
        this.canvasProjectService = canvasProjectService;
    }

    @GetMapping("/api/canvas/project")
    @Operation(summary = "读取画布项目")
    public JsonNode load() {
        return canvasProjectService.load();
    }

    @PutMapping("/api/canvas/project")
    @Operation(summary = "保存画布项目")
    public JsonNode save(@RequestBody JsonNode project) {
        return canvasProjectService.save(project);
    }

    @GetMapping("/api/canvas/mcp/tools")
    @Operation(summary = "MCP 工具清单（POC 占位）")
    public List<Map<String, String>> mcpTools() {
        return canvasProjectService.mcpTools();
    }
}
