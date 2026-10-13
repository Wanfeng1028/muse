package com.dramaauth.service;

import com.dramaauth.exception.ApiException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * JWT 服务：手写 HS256（离线仓库无 jjwt，只用 JDK + Jackson）。
 * 密钥必须来自环境变量 AUTH_JWT_SECRET，缺失则拒绝启动。
 */
@Service
public class JwtService {

    private final String secret;
    private final long accessTtlSeconds;
    private final long refreshTtlSeconds;
    private final ObjectMapper mapper = new ObjectMapper();

    public JwtService(
            @Value("${auth.jwt.secret:}") String secret,
            @Value("${auth.jwt.access-ttl-seconds:900}") long accessTtlSeconds,
            @Value("${auth.jwt.refresh-ttl-seconds:604800}") long refreshTtlSeconds) {
        this.secret = secret == null ? "" : secret.trim();
        this.accessTtlSeconds = accessTtlSeconds;
        this.refreshTtlSeconds = refreshTtlSeconds;
    }

    @PostConstruct
    void requireSecret() {
        if (secret.isEmpty()) {
            throw new IllegalStateException(
                    "AUTH_JWT_SECRET 未设置，auth-service 拒绝启动。请执行：export AUTH_JWT_SECRET=$(openssl rand -base64 48)");
        }
        if (secret.length() < 32) {
            throw new IllegalStateException("AUTH_JWT_SECRET 太短（至少 32 字符），请用 openssl rand -base64 48 生成");
        }
    }

    /** 签发 access token（15 分钟） */
    public AccessToken createAccessToken(Long userId, String role) {
        String jti = UUID.randomUUID().toString();
        return new AccessToken(createToken(userId, role, jti, accessTtlSeconds), jti);
    }

    public record AccessToken(String token, String jti) {
    }

    /** 签发 refresh token（7 天），返回 token 与 jti */
    public RefreshToken createRefreshToken(Long userId) {
        String jti = UUID.randomUUID().toString();
        return new RefreshToken(createToken(userId, "REFRESH", jti, refreshTtlSeconds), jti);
    }

    public record RefreshToken(String token, String jti) {
    }

    /** 验签并返回 claims；失败抛 401 */
    public Map<String, Object> parseAndValidate(String token) {
        try {
            String[] parts = token.split("\\.");
            if (parts.length != 3) {
                throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_TOKEN", "token 格式错误");
            }
            String signingInput = parts[0] + "." + parts[1];
            byte[] expected = hmac(signingInput);
            byte[] actual = base64UrlDecode(parts[2]);
            if (!MessageDigest.isEqual(expected, actual)) {
                throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_TOKEN", "token 签名无效");
            }
            Map<String, Object> claims = mapper.readValue(
                    base64UrlDecode(parts[1]), new TypeReference<Map<String, Object>>() {
                    });
            Object exp = claims.get("exp");
            long nowSec = System.currentTimeMillis() / 1000;
            if (!(exp instanceof Number) || ((Number) exp).longValue() <= nowSec) {
                throw new ApiException(HttpStatus.UNAUTHORIZED, "TOKEN_EXPIRED", "token 已过期");
            }
            return claims;
        } catch (ApiException e) {
            throw e;
        } catch (Exception e) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_TOKEN", "token 无效");
        }
    }

    private String createToken(Long userId, String role, String jti, long ttlSeconds) {
        try {
            long nowSec = System.currentTimeMillis() / 1000;
            Map<String, Object> header = Map.of("alg", "HS256", "typ", "JWT");
            Map<String, Object> payload = new HashMap<>();
            payload.put("sub", String.valueOf(userId));
            payload.put("role", role);
            payload.put("jti", jti);
            payload.put("iat", nowSec);
            payload.put("exp", nowSec + ttlSeconds);
            String h = base64UrlEncode(mapper.writeValueAsBytes(header));
            String p = base64UrlEncode(mapper.writeValueAsBytes(payload));
            String sig = base64UrlEncode(hmac(h + "." + p));
            return h + "." + p + "." + sig;
        } catch (Exception e) {
            throw new IllegalStateException("JWT 签发失败", e);
        }
    }

    private byte[] hmac(String data) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return mac.doFinal(data.getBytes(StandardCharsets.UTF_8));
    }

    private String base64UrlEncode(byte[] bytes) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private byte[] base64UrlDecode(String s) {
        return Base64.getUrlDecoder().decode(s);
    }
}
