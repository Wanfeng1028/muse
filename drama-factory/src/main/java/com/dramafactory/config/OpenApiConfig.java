package com.dramafactory.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.info.License;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

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
}
