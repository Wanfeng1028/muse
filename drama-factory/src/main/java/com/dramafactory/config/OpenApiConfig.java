package com.dramafactory.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.info.License;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

/**
 * OpenAPI 文档配置（v2.5 生产级补强第 4 轮）。
 *
 * <p>文档端点默认公开：{@code /v3/api-docs} 与 {@code /swagger-ui/**} 不在 {@code /api/**} 前缀下，
 * JwtAuthFilter 只拦 {@code /api/**}，所以这两个端点不需要 token 就能打开。
 * 部署时不要直接把服务暴露到公网，否则等于把整套接口清单和调用方式给别人看。</p>
 *
 * <p>securityScheme 里声明的 bearerAuth 只影响 swagger-ui 右上角那个 Authorize 按钮，
 * 让填了 token 之后 /api/** 的接口能直接在页面上试。没配置 AUTH_JWT_SECRET 时后端是开放模式，
 * 不带 token 也能调通。</p>
 * <p>下面按用途把接口拆成 4 组：runs 管 Run 和流水线状态，videos 管视频任务和成片这些产出，
 * scripts 管项目剧集分镜角色这些创作内容，admin 管认证、模型供应商、设置、用量和运维。
 * swagger-ui 右上角可以切组看，api-docs 地址也跟着变成 /v3/api-docs/{组名}。</p>
 */

@Configuration
@OpenAPIDefinition(
        info = @Info(
                title = "Drama Factory API",
                version = "v2.5",
                description = "AI 短剧生产管线的 HTTP API：项目、剧集、分镜、视频任务、成片、Run 全生命周期管理。",
                license = @License(name = "MIT", url = "https://opensource.org/licenses/MIT")
        ),
        security = @SecurityRequirement(name = "bearerAuth")
)
@SecurityScheme(
        name = "bearerAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT",
        description = "配置了 AUTH_JWT_SECRET 之后，/api/** 需要在请求头带上 Authorization: Bearer <token>。"
                + "没配置 AUTH_JWT_SECRET 时后端是开放模式，不带 token 也能访问。"
)
public class OpenApiConfig {

@Bean
@Order(1)
public GroupedOpenApi runsApi() {
    return GroupedOpenApi.builder()
        .group("runs")
        .displayName("运行管理")
        .pathsToMatch(
            "/api/runs/**",
            "/api/pipelines",
            "/api/projects/{projectId}/pipeline",
            "/api/projects/{projectId}/stats"
        )
        .build();
}

@Bean
@Order(2)
public GroupedOpenApi videosApi() {
    return GroupedOpenApi.builder()
        .group("videos")
        .displayName("视频生产")
        .pathsToMatch(
            "/api/video-tasks/**",
            "/api/shots/{shotId}/video-tasks",
            "/api/episodes/{episodeId}/video-tasks/submit-all",
            "/api/episodes/{episodeId}/final-cuts",
            "/api/final-cuts/**",
            "/api/mv/**",
            "/media/**",
            "/api/assets/**",
            "/api/tools/video/convert",
            "/api/tools/video/extract-audio"
        )
        .build();
}

@Bean
@Order(3)
public GroupedOpenApi scriptsApi() {
    return GroupedOpenApi.builder()
        .group("scripts")
        .displayName("剧本与内容")
        .pathsToMatch(
            "/api/projects/**",
            "/api/episodes/**",
            "/api/scenes/**",
            "/api/shots/**",
            "/api/characters/**",
            "/api/canvas/**",
            "/api/recipes/**"
        )
        .build();
}

@Bean
@Order(4)
public GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .displayName("系统管理")
        .pathsToMatch(
            "/api/agents/**",
            "/api/auth/**",
            "/api/byok/**",
            "/api/chat",
            "/api/health",
            "/api/official-skills/**",
            "/api/providers/**",
            "/api/settings/**",
            "/api/skillhub/**",
            "/api/skills/**",
            "/api/usage/**",
            "/api/tools/**",
            "/api/stats"
        )
        .build();
}

}

