package com.dramafactory.tools.controller;

import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetSource;
import com.dramafactory.model.AssetType;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.ProjectStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.repository.AssetRepository;
import com.dramafactory.service.EpisodeService;
import com.dramafactory.service.ProjectService;
import com.dramafactory.service.ShotService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QuickToolsControllerDeepTestR4 {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private AssetRepository assetRepository;

    @Autowired
    private ProjectService projectService;

    @Autowired
    private EpisodeService episodeService;

    @Autowired
    private ShotService shotService;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private String uniqueSuffix() {
        return "_" + System.nanoTime();
    }

    private Long createAsset() {
        Asset asset = new Asset();
        asset.setType(AssetType.IMAGE);
        asset.setSource(AssetSource.UPLOADED);
        String name = "r4-test-" + System.nanoTime() + ".png";
        asset.setFileName(name);
        asset.setFilePath("assets/" + name);
        return assetRepository.save(asset).getId();
    }

    private Long createEpisodeWithShot(int shotCount) {
        String suffix = uniqueSuffix();
        com.dramafactory.dto.Records.ProjectResponse project = projectService.create(
                new com.dramafactory.dto.Records.ProjectRequest(
                        "工具测试项目" + suffix, "都市", "简介" + suffix, ProjectStatus.DRAFT, 10));
        com.dramafactory.dto.Records.EpisodeResponse episode = episodeService.create(
                project.id(),
                new com.dramafactory.dto.Records.EpisodeRequest(
                        1, "第一集" + suffix, "大纲" + suffix, EpisodeStatus.DRAFT, 60));
        for (int i = 1; i <= shotCount; i++) {
            shotService.create(
                    episode.id(),
                    new com.dramafactory.dto.Records.ShotRequest(
                            i, null, null, "描述" + i + suffix, 5, "对白" + i, "提示" + i));
        }
        return episode.id();
    }

    private Long createEpisodeWithoutShot() {
        String suffix = uniqueSuffix();
        com.dramafactory.dto.Records.ProjectResponse project = projectService.create(
                new com.dramafactory.dto.Records.ProjectRequest(
                        "空剧集项目" + suffix, "都市", "简介" + suffix, ProjectStatus.DRAFT, 10));
        com.dramafactory.dto.Records.EpisodeResponse episode = episodeService.create(
                project.id(),
                new com.dramafactory.dto.Records.EpisodeRequest(
                        1, "空集" + suffix, "大纲" + suffix, EpisodeStatus.DRAFT, 60));
        return episode.id();
    }

    @Test
    void batchTag_merge_returnsCount() throws Exception {
        Long id1 = createAsset();
        Long id2 = createAsset();
        Map<String, Object> body = new HashMap<>();
        body.put("ids", List.of(id1, id2));
        body.put("tags", "夜景,雨");
        body.put("mode", "merge");
        mockMvc.perform(post("/api/tools/assets/batch-tag")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(2));
    }

    @Test
    void batchTag_replace_returnsCount() throws Exception {
        Long id1 = createAsset();
        Long id2 = createAsset();
        Map<String, Object> body = new HashMap<>();
        body.put("ids", List.of(id1, id2));
        body.put("tags", "白天,晴");
        body.put("mode", "replace");
        mockMvc.perform(post("/api/tools/assets/batch-tag")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(2));
    }

    @Test
    void batchTag_nullMode_defaultsMerge() throws Exception {
        Long id1 = createAsset();
        Long id2 = createAsset();
        Map<String, Object> body = new HashMap<>();
        body.put("ids", List.of(id1, id2));
        body.put("tags", "默认");
        body.put("mode", null);
        mockMvc.perform(post("/api/tools/assets/batch-tag")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(2));
    }

    @Test
    void batchTag_emptyIds_returns400() throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("ids", List.of());
        body.put("tags", "a");
        body.put("mode", "merge");
        mockMvc.perform(post("/api/tools/assets/batch-tag")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void batchTag_badMode_returns400() throws Exception {
        Long id1 = createAsset();
        Map<String, Object> body = new HashMap<>();
        body.put("ids", List.of(id1));
        body.put("tags", "a");
        body.put("mode", "append");
        mockMvc.perform(post("/api/tools/assets/batch-tag")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void batchTag_unknownId_returns404() throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("ids", List.of(999999999L));
        body.put("tags", "a");
        body.put("mode", "merge");
        mockMvc.perform(post("/api/tools/assets/batch-tag")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isNotFound());
    }

    @Test
    void batchRename_valid_returnsCount() throws Exception {
        Long id1 = createAsset();
        Long id2 = createAsset();
        Map<String, String> renames = new HashMap<>();
        renames.put(String.valueOf(id1), "新名1" + uniqueSuffix());
        renames.put(String.valueOf(id2), "新名2" + uniqueSuffix());
        Map<String, Object> body = new HashMap<>();
        body.put("renames", renames);
        mockMvc.perform(post("/api/tools/assets/batch-rename")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(2));
    }

    @Test
    void batchRename_empty_returns400() throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("renames", new HashMap<String, String>());
        mockMvc.perform(post("/api/tools/assets/batch-rename")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void exportShotsCsv_valid_returnsCsv() throws Exception {
        Long episodeId = createEpisodeWithShot(1);
        mockMvc.perform(get("/api/tools/episodes/{id}/shots.csv", episodeId))
                .andExpect(status().isOk())
                .andExpect(header().string("Content-Type",
                        org.hamcrest.Matchers.containsString("text/csv")))
                .andExpect(header().string("Content-Disposition",
                        org.hamcrest.Matchers.containsString("shots-episode-" + episodeId + ".csv")))
                .andExpect(result -> {
                    byte[] bytes = result.getResponse().getContentAsByteArray();
                    assertThat(bytes).isNotEmpty();
                });
    }

    @Test
    void exportShotsCsv_emptyEpisode_returnsCsv() throws Exception {
        Long episodeId = createEpisodeWithoutShot();
        mockMvc.perform(get("/api/tools/episodes/{id}/shots.csv", episodeId))
                .andExpect(status().isOk())
                .andExpect(header().string("Content-Type",
                        org.hamcrest.Matchers.containsString("text/csv")));
    }

    @Test
    void opLogs_returnsList() throws Exception {
        Long id1 = createAsset();
        Map<String, Object> body = new HashMap<>();
        body.put("ids", List.of(id1));
        body.put("tags", "日志");
        body.put("mode", "merge");
        mockMvc.perform(post("/api/tools/assets/batch-tag")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/tools/op-logs"))
                .andExpect(status().isOk())
                .andExpect(result -> {
                    String json = result.getResponse().getContentAsString();
                    com.fasterxml.jackson.databind.JsonNode node = objectMapper.readTree(json);
                    assertThat(node.isArray()).isTrue();
                    assertThat(node.size()).isGreaterThanOrEqualTo(1);
                });
    }

    @Test
    void batchTag_wrongMethod_returns500DueToGlobalHandler() throws Exception {
        // 真实行为：HttpRequestMethodNotSupportedException 被 GlobalExceptionHandler 的
        // @ExceptionHandler(Exception.class) 捕获，转为 500（而非标准的 405）
        mockMvc.perform(get("/api/tools/assets/batch-tag"))
                .andExpect(status().isInternalServerError());
    }
}