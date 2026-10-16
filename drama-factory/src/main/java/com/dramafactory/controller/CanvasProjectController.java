package com.dramafactory.controller;

import com.dramafactory.dto.canvas.CanvasJobV2;
import com.dramafactory.dto.canvas.CanvasPatchRequest;
import com.dramafactory.dto.canvas.CanvasProposalV2;
import com.dramafactory.dto.canvas.CanvasProjectV2;
import com.dramafactory.service.CanvasEventService;
import com.dramafactory.service.CanvasJobService;
import com.dramafactory.service.CanvasProjectService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.Map;

@RestController
@Tag(name = "Canvas", description = "编排画布项目 JSON 的读写接口")
public class CanvasProjectController {

    private final CanvasProjectService canvasProjectService;
    private final CanvasEventService canvasEventService;
    private final CanvasJobService canvasJobService;
    private final ObjectMapper objectMapper;

    public CanvasProjectController(CanvasProjectService canvasProjectService,
                                   CanvasEventService canvasEventService,
                                   CanvasJobService canvasJobService,
                                   ObjectMapper objectMapper) {
        this.canvasProjectService = canvasProjectService;
        this.canvasEventService = canvasEventService;
        this.canvasJobService = canvasJobService;
        this.objectMapper = objectMapper;
    }

    @GetMapping("/api/canvas")
    @Operation(summary = "读取画布项目（v2，带 ETag）")
    @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "304", description = "If-None-Match 版本一致，无变更")
    public ResponseEntity<CanvasProjectV2> getCanvas(
            @RequestHeader(value = HttpHeaders.IF_NONE_MATCH, required = false) String ifNoneMatch) {

        CanvasProjectV2 project = canvasProjectService.loadV2();
        String etag = "\"" + project.version() + "\"";
        if (ifNoneMatch != null) {
            String v = ifNoneMatch.trim();
            if (v.startsWith("W/")) {
                v = v.substring(2);
            }
            if (v.startsWith("\"") && v.endsWith("\"") && v.length() >= 2) {
                v = v.substring(1, v.length() - 1);
            }
            if (v.equals(String.valueOf(project.version()))) {
                return ResponseEntity.status(HttpStatus.NOT_MODIFIED)
                        .eTag(etag)
                        .build();
            }
        }
        return ResponseEntity.ok().eTag(etag).body(project);
    }

    @GetMapping("/api/canvas/project")
    @Operation(summary = "读取画布项目（兼容旧 React bundle，附带 revision）")
    public JsonNode load() {
        CanvasProjectV2 project = canvasProjectService.loadV2();
        ObjectNode node = objectMapper.valueToTree(project);
        node.put("revision", project.version());
        return node;
    }

    @PutMapping("/api/canvas/project")
    @Operation(summary = "保存画布项目")
    public CanvasProjectV2 save(@RequestBody JsonNode project) {
        return canvasProjectService.saveV2(project, "editor");
    }

    @PatchMapping("/api/canvas")
    @Operation(summary = "增量修改画布项目（白名单字段）")
    public CanvasProjectV2 patch(@RequestBody CanvasPatchRequest req,
                                 @RequestHeader(value = "If-Match", required = false) String ifMatch) {
        return canvasProjectService.applyPatch(req, ifMatch, "agent");
    }

    @GetMapping(value = "/api/canvas/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @Operation(summary = "画布事件流（SSE）")
    public SseEmitter events() {
        return canvasEventService.subscribe(canvasProjectService.currentVersion());
    }

    @PostMapping("/api/canvas/proposals")
    @Operation(summary = "提交 proposal（切片 1 仅预留）")
    @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "202", description = "已接受，返回创建的 proposal")
    public ResponseEntity<CanvasProposalV2> createProposal(@RequestBody JsonNode body) {

        CanvasProposalV2 proposal = canvasProjectService.createProposal(body);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(proposal);
    }

    @GetMapping("/api/canvas/proposals")
    @Operation(summary = "列出 proposal")
    public List<CanvasProposalV2> listProposals() {
        return canvasProjectService.listProposals();
    }

    @PostMapping("/api/canvas/jobs")
    @Operation(summary = "创建 job")
    @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "202", description = "已接受，返回创建的 job")
    public ResponseEntity<CanvasJobV2> createJob(@RequestBody(required = false) JsonNode body) {

        String nodeId = null;
        if (body != null && body.has("node_id") && body.get("node_id").isTextual()) {
            nodeId = body.get("node_id").asText();
        }
        CanvasJobV2 job = canvasJobService.createJob(nodeId);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(job);
    }

    @GetMapping("/api/canvas/jobs/{jobId}")
    @Operation(summary = "查询 job")
    public CanvasJobV2 getJob(@PathVariable String jobId) {
        return canvasJobService.getJob(jobId);
    }

    @GetMapping("/api/canvas/mcp/tools")
    @Operation(summary = "MCP 工具清单（POC 占位）")
    public List<Map<String, String>> mcpTools() {
        return canvasProjectService.mcpTools();
    }
}
