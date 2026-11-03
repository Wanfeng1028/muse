package com.dramafactory.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * ByokController 的参数校验与文件下载安全测试。
 * 不触发任何真实生成调用。
 */
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class ByokControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void generateIllegalModuleIs400() throws Exception {
        mockMvc.perform(post("/api/byok/generate")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"module\":\"VIDEO\",\"providerId\":1,\"modelId\":\"m\",\"prompt\":\"hi\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value("FAILED"));
    }

    @Test
    void generateMissingProviderIdIs400() throws Exception {
        mockMvc.perform(post("/api/byok/generate")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"module\":\"IMAGE\",\"modelId\":\"m\",\"prompt\":\"hi\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value("FAILED"));
    }

    @Test
    void generateBlankPromptIs400() throws Exception {
        mockMvc.perform(post("/api/byok/generate")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"module\":\"IMAGE\",\"providerId\":1,\"modelId\":\"m\",\"prompt\":\"  \"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("请填写提示词"));
    }

    @Test
    void generateUnknownProviderIs404() throws Exception {
        mockMvc.perform(post("/api/byok/generate")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"module\":\"IMAGE\",\"providerId\":999999,\"modelId\":\"m\",\"prompt\":\"hi\"}"))
                .andExpect(status().isNotFound());
    }

    @Test
    void fileIllegalModuleIs400() throws Exception {
        mockMvc.perform(get("/api/byok/file/video/x.png"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void filePathTraversalIs400() throws Exception {
        mockMvc.perform(get("/api/byok/file/image/..%2F..%2Fsecret"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void fileNotFoundIs404() throws Exception {
        mockMvc.perform(get("/api/byok/file/image/does-not-exist.png"))
                .andExpect(status().isNotFound());
    }
}
