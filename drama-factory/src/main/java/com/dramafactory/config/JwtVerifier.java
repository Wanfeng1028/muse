package com.dramafactory.config;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.Map;

/**
 * JWT 验签（资源方）：手写 HS256 校验，与 auth-service 同密钥。
 * 离线仓库无 jjwt，只用 JDK + Jackson。
 */
@Component
public class JwtVerifier {

    private final String secret;
    private final ObjectMapper mapper = new ObjectMapper();

    public JwtVerifier(@Value("${auth.jwt.secret:}") String secret) {
        this.secret = secret == null ? "" : secret.trim();
    }

    /** 是否启用鉴权：secret 为空时为开放模式（单机本地使用） */
    public boolean isEnabled() {
        return !secret.isEmpty();
    }

    /**
     * 验签并返回 claims；失败返回 null（不抛异常，由 filter 统一 401）。
     * 拒绝 refresh token（role=REFRESH）调业务接口。
     */
    public Map<String, Object> verify(String token) {
        try {
            if (token == null) {
                return null;
            }
            String[] parts = token.split("\\.");
            if (parts.length != 3) {
                return null;
            }
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            byte[] expected = mac.doFinal((parts[0] + "." + parts[1]).getBytes(StandardCharsets.UTF_8));
            byte[] actual = Base64.getUrlDecoder().decode(parts[2]);
            if (!MessageDigest.isEqual(expected, actual)) {
                return null;
            }
            Map<String, Object> claims = mapper.readValue(
                    Base64.getUrlDecoder().decode(parts[1]),
                    new TypeReference<Map<String, Object>>() {
                    });
            Object exp = claims.get("exp");
            long nowSec = System.currentTimeMillis() / 1000;
            if (!(exp instanceof Number) || ((Number) exp).longValue() <= nowSec) {
                return null;
            }
            if ("REFRESH".equals(claims.get("role"))) {
                return null;
            }
            return claims;
        } catch (Exception e) {
            return null;
        }
    }
}
