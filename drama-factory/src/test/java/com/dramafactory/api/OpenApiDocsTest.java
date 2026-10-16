package com.dramafactory.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;


import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * OpenAPI 文档端点测试（v2.5 生产级补强第 4 轮）。
 *
 * <p>MockMvc 边界说明：springdoc 的文档端点本身就是 Spring MVC 的 @RestController，
 * 走的是 DispatcherServlet 的正常分发链路，不依赖真实网络栈，所以用 MockMvc 直接驱动即可，
 * 不需要 RANDOM_PORT、不需要 TestRestTemplate、不需要起真实 HTTP 服务。</p>
 *
 * <p>注意：{@code /v3/api-docs} 与 {@code /swagger-ui/**} 都不在 {@code /api/**} 前缀下，
 * 所以不会被 JwtAuthFilter 拦。这里也顺带验证了这一点（不带 token 能 200）。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocsTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    /**
     * 场景一：GET /v3/api-docs 返回合法 OpenAPI 3.x JSON，且关键路径都在。
     */
    @Test
    void apiDocs_returnsOpenApiJsonWithExpectedPaths() throws Exception {
        MvcResult result = mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andReturn();

        String body = result.getResponse().getContentAsString();
        assertThat(body).isNotBlank();

        JsonNode root = objectMapper.readTree(body);

        // 1) openapi 版本号必须以 "3." 开头
        JsonNode openapiNode = root.get("openapi");
        assertThat(openapiNode)
                .as("/v3/api-docs 响应里必须有 openapi 字段")
                .isNotNull();
        assertThat(openapiNode.asText())
                .as("openapi 版本应以 3. 开头")
                .startsWith("3.");

        // 2) info.title 必须是配置里写死的 "Drama Factory API"
        JsonNode infoNode = root.get("info");
        assertThat(infoNode)
                .as("/v3/api-docs 响应里必须有 info 字段")
                .isNotNull();
        assertThat(infoNode.path("title").asText())
                .as("info.title 应等于 OpenApiConfig 中声明的标题")
                .isEqualTo("Drama Factory API");
        assertThat(infoNode.path("version").asText())
                .as("info.version 应等于 v2.5")
                .isEqualTo("v2.5");

        // 3) paths 至少包含这四个 key
        JsonNode pathsNode = root.get("paths");
        assertThat(pathsNode)
                .as("/v3/api-docs 响应里必须有 paths 字段")
                .isNotNull();
        assertThat(pathsNode.isObject())
                .as("paths 必须是一个 JSON 对象")
                .isTrue();

        Set<String> pathKeys = new HashSet<>();
        Iterator<String> fieldNames = pathsNode.fieldNames();
        while (fieldNames.hasNext()) {
            pathKeys.add(fieldNames.next());
        }

        assertThat(pathKeys)
                .as("paths 里应至少包含这四个路径")
                .contains("/api/projects", "/api/runs", "/api/health",
                        "/api/episodes/{id}/generate-script");
    }

    /**
     * 场景二：swagger-ui 静态页面可达（springdoc 打包的 swagger-ui 入口页）。
     */
    @Test
    void swaggerUi_indexIsReachable() throws Exception {
        MvcResult result = mockMvc.perform(get("/swagger-ui/index.html"))
                .andExpect(status().isOk())
                .andReturn();

        assertThat(result.getResponse().getContentType())
                .as("swagger-ui 首页应返回 HTML")
                .isNotNull()
                .contains(MediaType.TEXT_HTML_VALUE);

        String html = result.getResponse().getContentAsString();
        assertThat(html)
                .as("swagger-ui 首页 HTML 里应出现 swagger 字样")
                .containsIgnoringCase("swagger");
    }

    @Test
    void apiDocsGroups_allFourReachable() throws Exception {
        for (String group : List.of("runs", "videos", "scripts", "admin")) {
            String body = mockMvc.perform(get("/v3/api-docs/" + group))
                    .andExpect(status().isOk())
                    .andReturn()
                    .getResponse()
                    .getContentAsString();

            assertThat(body)
                    .as("分组 %s 的 OpenAPI 文档响应体不应为空", group)
                    .isNotBlank();

            JsonNode root = objectMapper.readTree(body);
            assertThat(root.path("openapi").asText())
                    .as("分组 %s 的 openapi 版本应以 3. 开头", group)
                    .startsWith("3.");
        }
    }

    @Test
    void apiDocsGroups_containExpectedPaths() throws Exception {
        Map<String, List<String>> expectedPathsByGroup = Map.of(
                "runs", List.of("/api/runs", "/api/runs/{id}/pause"),
                "videos", List.of("/api/video-tasks/{taskId}", "/media/videos/{taskId}"),
                "scripts", List.of("/api/projects", "/api/episodes/{id}/generate-script"),
                "admin", List.of("/api/health", "/api/settings/effective-provider")
        );

        for (Map.Entry<String, List<String>> entry : expectedPathsByGroup.entrySet()) {
            String group = entry.getKey();
            String body = mockMvc.perform(get("/v3/api-docs/" + group))
                    .andExpect(status().isOk())
                    .andReturn()
                    .getResponse()
                    .getContentAsString();

            JsonNode paths = objectMapper.readTree(body).path("paths");
            for (String expectedPath : entry.getValue()) {
                assertThat(paths.has(expectedPath))
                        .as("分组 %s 的文档 paths 应包含 %s", group, expectedPath)
                        .isTrue();
            }
        }
    }
}

