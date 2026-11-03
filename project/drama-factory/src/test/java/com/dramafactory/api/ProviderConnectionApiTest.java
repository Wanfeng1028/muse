package com.dramafactory.api;

import com.dramafactory.model.MediaProvider;
import com.dramafactory.repository.MediaProviderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 供应商连接自检 API 契约测试：全部走 mock 提供方或 UNSUPPORTED 路径，零真实网络。
 */
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class ProviderConnectionApiTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private MediaProviderRepository mediaProviderRepository;

    private Long saveProvider(String name, String module) {
        MediaProvider p = new MediaProvider();
        p.setName(name);
        p.setModule(module);
        return mediaProviderRepository.save(p).getId();
    }

    @Test
    void testMockProviderReturnsOk() throws Exception {
        Long id = saveProvider("演示 mock", "VIDEO");
        mockMvc.perform(post("/api/providers/" + id + "/test"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("OK"));
    }

    @Test
    void testImageModuleReturnsUnsupported() throws Exception {
        Long id = saveProvider("演示 mock", "IMAGE");
        mockMvc.perform(post("/api/providers/" + id + "/test"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UNSUPPORTED"));
    }

    @Test
    void testUnknownVideoNameReturnsUnsupported() throws Exception {
        Long id = saveProvider("某不知名厂商", "VIDEO");
        mockMvc.perform(post("/api/providers/" + id + "/test"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UNSUPPORTED"));
    }

    @Test
    void testNotFoundReturns404() throws Exception {
        mockMvc.perform(post("/api/providers/999999999/test"))
                .andExpect(status().isNotFound());
    }
}
