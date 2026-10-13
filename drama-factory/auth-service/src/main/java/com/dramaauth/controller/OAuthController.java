package com.dramaauth.controller;

import com.dramaauth.service.AuthService;
import com.dramaauth.service.OAuthService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * OAuth 登录：授权 URL 下发与回调。
 * 未配置凭证的渠道返回 501 OAUTH_NOT_CONFIGURED，handshake 未实测，不伪造。
 */
@RestController
@RequestMapping("/api/auth/oauth")
public class OAuthController {

    private final OAuthService oauthService;

    public OAuthController(OAuthService oauthService) {
        this.oauthService = oauthService;
    }

    /** 取授权 URL：GET /api/auth/oauth/{google|github|apple}/url */
    @GetMapping("/{provider}/url")
    public Map<String, String> authUrl(@PathVariable String provider) {
        return Map.of("url", oauthService.authUrl(provider));
    }

    /** 回调：GET /api/auth/oauth/{provider}/callback?code=...&state=... */
    @GetMapping("/{provider}/callback")
    public ResponseEntity<Map<String, Object>> callback(
            @PathVariable String provider,
            @RequestParam(required = false) String code,
            @RequestParam(required = false) String state,
            HttpServletRequest request) {
        AuthService.TokenPair pair = oauthService.callback(
                provider, code, state, request.getRemoteAddr());
        return ResponseEntity.ok(Map.of(
                "accessToken", pair.accessToken(),
                "refreshToken", pair.refreshToken(),
                "expiresIn", pair.expiresIn(),
                "tokenType", "Bearer"));
    }

    /** 支持的渠道清单 */
    @GetMapping("/providers")
    public List<String> providers() {
        return OAuthService.PROVIDERS;
    }
}
