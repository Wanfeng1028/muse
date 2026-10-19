package com.dramafactory.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class ReviewApiTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;


    // ---------- 夹具 ----------

    private long createProject() throws Exception {
        String body = "{\"title\":\"T\",\"genre\":\"drama\",\"synopsis\":\"s\",\"targetEpisodes\":3}";
        String resp = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return objectMapper.readTree(resp).get("id").asLong();
    }

    private long createEpisode(long projectId) throws Exception {
        String body = "{\"episodeNo\":1,\"title\":\"E1\",\"outline\":\"o\",\"status\":null,\"durationSec\":null}";
        String resp = mockMvc.perform(post("/api/projects/" + projectId + "/episodes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return objectMapper.readTree(resp).get("id").asLong();
    }

    private String submitBody(String kind, int version) {
        return "{\"kind\":\"" + kind + "\",\"version\":" + version + "}";
    }

    private String actionBody(int version, String comment) {
        if (comment == null) {
            return "{\"version\":" + version + "}";
        }
        return "{\"version\":" + version + ",\"comment\":\"" + comment + "\"}";
    }

    // ---------- 全链路 ----------

    @Test
    void fullScriptFlow_singleUser_selfReviewedTrue() throws Exception {
        long pid = createProject();
        long eid = createEpisode(pid);

        // submit
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/submit")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(submitBody("SCRIPT", 0)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("PENDING_L1"));

        // l1Approve
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/script/l1/approve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(actionBody(1, "写得不错")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("PENDING_L2"));

        // l2Approve
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/script/l2/approve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(actionBody(2, "通过")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("APPROVED"));

        // 详情：一人走完两级 → selfReviewed=true
        mockMvc.perform(get("/api/projects/" + pid + "/episodes/" + eid + "/review")
                        .param("kind", "SCRIPT"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("APPROVED"))
                .andExpect(jsonPath("$.selfReviewed").value(true));

        // 历史 3 行，事件顺序
        mockMvc.perform(get("/api/projects/" + pid + "/episodes/" + eid + "/review/history")
                        .param("kind", "SCRIPT")
                        .param("page", "0")
                        .param("size", "20"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(3)))
                .andExpect(jsonPath("$[0].event").value("SUBMIT"))
                .andExpect(jsonPath("$[1].event").value("L1_APPROVE"))
                .andExpect(jsonPath("$[2].event").value("L2_APPROVE"));
    }

    // ---------- 非法流转 409 ----------

    @Test
    void approvedThenL1Approve_conflict409() throws Exception {
        long pid = createProject();
        long eid = createEpisode(pid);

        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/submit")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(submitBody("SCRIPT", 0)))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/script/l1/approve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(actionBody(1, null)))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/script/l2/approve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(actionBody(2, null)))
                .andExpect(status().isOk());

        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/script/l1/approve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(actionBody(3, null)))
                .andExpect(status().isConflict());
    }

    // ---------- 版本冲突 409 ----------

    @Test
    void staleVersion_conflict409() throws Exception {
        long pid = createProject();
        long eid = createEpisode(pid);

        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/submit")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(submitBody("SCRIPT", 0)))
                .andExpect(status().isOk());

        // 当前 version 已是 1，用 version=0 调 l1Approve → 409
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/script/l1/approve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(actionBody(0, null)))
                .andExpect(status().isConflict());
    }

    // ---------- 越权 403 / queue 不过滤抛错 ----------

    @Test
    void crossProject_forbidden403() throws Exception {
        // user-a 建项目与剧集
        long pid = createProject();
        long eid = createEpisode(pid);

        // user-b 调 submit → 403
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/submit")
                        .contentType(MediaType.APPLICATION_JSON)
                        .requestAttr("auth.userId", "user-b")
                        .content(submitBody("SCRIPT", 0)))
                .andExpect(status().isForbidden());

        // user-b 调 GET /review → 403
        mockMvc.perform(get("/api/projects/" + pid + "/episodes/" + eid + "/review")
                        .requestAttr("auth.userId", "user-b")
                        .param("kind", "SCRIPT"))
                .andExpect(status().isForbidden());

        // user-b 调 queue → 空列表（只返回自己的，不过滤抛错）
        mockMvc.perform(get("/api/projects/" + pid + "/review/queue")
                        .requestAttr("auth.userId", "user-b")
                        .param("kind", "SCRIPT")
                        .param("status", "PENDING_L1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(0)));
    }

    // ---------- BOARD 流 ----------

    @Test
    void boardFlow_submit_approve_toApproved() throws Exception {
        long pid = createProject();
        long eid = createEpisode(pid);

        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/submit")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(submitBody("BOARD", 0)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("PENDING"));

        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/board/approve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(actionBody(1, "ok")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("APPROVED"));
    }

    // ---------- queue 命中 ----------

    @Test
    void queue_pendingL1_hitsOne() throws Exception {
        long pid = createProject();
        long eid = createEpisode(pid);

        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/submit")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(submitBody("SCRIPT", 0)))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/projects/" + pid + "/review/queue")
                        .param("kind", "SCRIPT")
                        .param("status", "PENDING_L1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].episodeTitle").value("E1"));
    }

    @Test
    void scriptL1Reject_backToDraft() throws Exception {
        long pid = createProject();
        long eid = createEpisode(pid);
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/submit")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(submitBody("SCRIPT", 0)))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/script/l1/reject")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(actionBody(1, "结构有问题")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("DRAFT"));
        mockMvc.perform(get("/api/projects/" + pid + "/episodes/" + eid + "/review")
                        .param("kind", "SCRIPT"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("DRAFT"));
    }

    @Test
    void scriptL2Reject_toRejected() throws Exception {
        long pid = createProject();
        long eid = createEpisode(pid);
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/submit")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(submitBody("SCRIPT", 0)))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/script/l1/approve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(actionBody(1, "通过")))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/script/l2/reject")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(actionBody(2, null)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("REJECTED"));
        mockMvc.perform(get("/api/projects/" + pid + "/episodes/" + eid + "/review")
                        .param("kind", "SCRIPT"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("REJECTED"));
    }

    @Test
    void boardReject_backToDraft() throws Exception {
        long pid = createProject();
        long eid = createEpisode(pid);
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/submit")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(submitBody("BOARD", 0)))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/projects/" + pid + "/episodes/" + eid + "/review/board/reject")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(actionBody(1, "分镜太碎")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("DRAFT"));
        mockMvc.perform(get("/api/projects/" + pid + "/episodes/" + eid + "/review")
                        .param("kind", "BOARD"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("DRAFT"));
    }
}