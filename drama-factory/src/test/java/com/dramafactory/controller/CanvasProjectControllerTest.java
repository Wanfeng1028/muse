package com.dramafactory.controller;

import com.dramafactory.config.JwtVerifier;
import com.dramafactory.exception.CanvasConflictException;
import com.dramafactory.service.CanvasProjectService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CanvasProjectController.class)
class CanvasProjectControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private CanvasProjectService canvasProjectService;

    @MockBean
    private JwtVerifier jwtVerifier;

    @Test
    void getProject_returnsProjectJson() throws Exception {
        JsonNode project = objectMapper.readTree(
                "{\"version\":1,\"nodes\":[{\"id\":\"n1\"}],\"edges\":[]}");
        when(canvasProjectService.load()).thenReturn(project);

        mockMvc.perform(get("/api/canvas/project"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value(1))
                .andExpect(jsonPath("$.nodes[0].id").value("n1"))
                .andExpect(jsonPath("$.edges").isArray());
    }

    @Test
    void putProject_validPayload_returns200() throws Exception {
        JsonNode project = objectMapper.readTree(
                "{\"version\":1,\"nodes\":[],\"edges\":[]}");
        when(canvasProjectService.save(any(JsonNode.class), eq("editor"))).thenReturn(project);

        mockMvc.perform(put("/api/canvas/project")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"version\":1,\"nodes\":[],\"edges\":[]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value(1));
    }

    @Test
    void putProject_missingVersion_returns400() throws Exception {
        when(canvasProjectService.save(any(JsonNode.class), eq("editor")))
                .thenThrow(new IllegalArgumentException("画布项目格式不对：需要 version/nodes/edges"));

        mockMvc.perform(put("/api/canvas/project")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"nodes\":[],\"edges\":[]}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void putProject_nodesNotArray_returns400() throws Exception {
        when(canvasProjectService.save(any(JsonNode.class), eq("editor")))
                .thenThrow(new IllegalArgumentException("画布项目格式不对：需要 version/nodes/edges"));

        mockMvc.perform(put("/api/canvas/project")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"version\":1,\"nodes\":{},\"edges\":[]}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void getMcpTools_returnsThreeTools() throws Exception {
        List<Map<String, String>> tools = new ArrayList<>();

        Map<String, String> getTool = new LinkedHashMap<>();
        getTool.put("name", "canvas.get_project");
        getTool.put("description", "读取当前编排画布的项目 JSON，返回版本号、节点列表和连线列表。");
        getTool.put("inputSchema", "{\"type\":\"object\",\"properties\":{},\"additionalProperties\":false}");
        tools.add(getTool);

        Map<String, String> saveTool = new LinkedHashMap<>();
        saveTool.put("name", "canvas.save_project");
        saveTool.put("description", "把整份画布项目 JSON 覆盖保存到磁盘，要求 version 为 1，nodes 和 edges 都是数组。");
        saveTool.put("inputSchema", "{\"type\":\"object\",\"properties\":{\"project\":{\"type\":\"object\"}},\"required\":[\"project\"],\"additionalProperties\":false}");
        tools.add(saveTool);

        Map<String, String> applyPatchTool = new LinkedHashMap<>();
        applyPatchTool.put("name", "canvas.apply_patch");
        applyPatchTool.put("description", "对画布项目做增量修改（RFC 6902 JSON Patch），请求体必须带 base_version，版本过期返回 409。POC 阶段仅定接口，真实执行随网关 POC 落地。");
        applyPatchTool.put("inputSchema", "{\"type\":\"object\",\"properties\":{\"base_version\":{\"type\":\"integer\"},\"patch\":{\"type\":\"array\"}},\"required\":[\"base_version\",\"patch\"],\"additionalProperties\":false}");
        tools.add(applyPatchTool);

        when(canvasProjectService.mcpTools()).thenReturn(tools);

        mockMvc.perform(get("/api/canvas/mcp/tools"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(3))
                .andExpect(jsonPath("$[0].name").value("canvas.get_project"))
                .andExpect(jsonPath("$[1].name").value("canvas.save_project"))
                .andExpect(jsonPath("$[2].name").value("canvas.apply_patch"));
    }

    @Test
    void putConflict_returns409WithVersionFields() throws Exception {
        when(canvasProjectService.save(any(JsonNode.class), eq("editor")))
                .thenThrow(new CanvasConflictException(3, "agent"));

        mockMvc.perform(put("/api/canvas/project")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"base_version\":2,\"version\":1,\"nodes\":[],\"edges\":[]}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.current_version").value(3))
                .andExpect(jsonPath("$.updated_by").value("agent"));
    }
}
