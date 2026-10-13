package com.dramaauth.controller;

import com.dramaauth.security.AuthInterceptor;
import com.dramaauth.service.AuthService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 账号 API：注册/登录/刷新/登出/资料/密码/邮箱/会话。
 * 未登录调受保护接口 → 401；API 未授权一律 401（页面重定向由前端负责）。
 */
@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    /* ---------- 请求体 ---------- */

    public record RegisterRequest(
            @Email @NotBlank String email,
            @NotBlank String password,
            @NotBlank String nickname) {
    }

    public record LoginRequest(
            @Email @NotBlank String email,
            @NotBlank String password) {
    }

    public record RefreshRequest(@NotBlank String refreshToken) {
    }

    public record ProfileRequest(String nickname, String avatarUrl) {
    }

    public record PasswordRequest(@NotBlank String oldPassword, @NotBlank String newPassword) {
    }

    public record EmailRequest(@Email @NotBlank String newEmail, @NotBlank String password) {
    }

    public record TokenResponse(String accessToken, String refreshToken, long expiresIn, String tokenType) {
    }

    /* ---------- 公开 ---------- */

    @PostMapping("/register")
    public ResponseEntity<AuthService.UserDto> register(@Valid @RequestBody RegisterRequest req) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(authService.register(req.email(), req.password(), req.nickname()));
    }

    @PostMapping("/login")
    public ResponseEntity<TokenResponse> login(
            @Valid @RequestBody LoginRequest req,
            @RequestHeader(value = "User-Agent", required = false) String userAgent,
            HttpServletRequest request) {
        AuthService.TokenPair pair = authService.login(
                req.email(), req.password(), userAgent, request.getRemoteAddr());
        return ResponseEntity.ok(new TokenResponse(
                pair.accessToken(), pair.refreshToken(), pair.expiresIn(), "Bearer"));
    }

    @PostMapping("/refresh")
    public ResponseEntity<TokenResponse> refresh(@Valid @RequestBody RefreshRequest req) {
        AuthService.TokenPair pair = authService.refresh(req.refreshToken());
        return ResponseEntity.ok(new TokenResponse(
                pair.accessToken(), pair.refreshToken(), pair.expiresIn(), "Bearer"));
    }

    /* ---------- 需登录 ---------- */

    private Long userId(HttpServletRequest request) {
        return (Long) request.getAttribute(AuthInterceptor.ATTR_USER_ID);
    }

    private String bearer(HttpServletRequest request) {
        String h = request.getHeader("Authorization");
        return h != null && h.startsWith("Bearer ") ? h.substring(7) : "";
    }

    @PostMapping("/logout")
    public ResponseEntity<Void> logout(HttpServletRequest request) {
        authService.logout(bearer(request));
        return ResponseEntity.ok().build();
    }

    @GetMapping("/me")
    public AuthService.UserDto me(HttpServletRequest request) {
        return authService.me(userId(request));
    }

    @PutMapping("/profile")
    public AuthService.UserDto updateProfile(@RequestBody ProfileRequest req, HttpServletRequest request) {
        return authService.updateProfile(userId(request),
                req == null ? null : req.nickname(), req == null ? null : req.avatarUrl());
    }

    @PutMapping("/password")
    public ResponseEntity<Void> changePassword(@Valid @RequestBody PasswordRequest req,
                                              HttpServletRequest request) {
        authService.changePassword(userId(request), req.oldPassword(), req.newPassword());
        return ResponseEntity.ok().build();
    }

    @PutMapping("/email")
    public AuthService.UserDto changeEmail(@Valid @RequestBody EmailRequest req,
                                           HttpServletRequest request) {
        return authService.changeEmail(userId(request), req.newEmail(), req.password());
    }

    @GetMapping("/sessions")
    public List<AuthService.SessionDto> sessions(HttpServletRequest request) {
        return authService.listSessions(userId(request));
    }

    @DeleteMapping("/sessions/{id}")
    public ResponseEntity<Void> revokeSession(@PathVariable Long id, HttpServletRequest request) {
        authService.revokeSession(userId(request), id);
        return ResponseEntity.noContent().build();
    }
}
