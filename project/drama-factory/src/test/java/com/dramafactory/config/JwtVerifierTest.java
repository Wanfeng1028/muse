package com.dramafactory.config;

import org.junit.jupiter.api.Test;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * JwtVerifier 单元测试（纯 JDK 签名，不依赖 Spring 上下文）。
 */
class JwtVerifierTest {

    private static final String SECRET = "unit-test-secret-0123456789abcdef";

    private static String b64(String s) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(s.getBytes(StandardCharsets.UTF_8));
    }

    /** 测试内手签一个 token */
    private static String sign(String sub, String role, long ttlSec) throws Exception {
        long now = System.currentTimeMillis() / 1000;
        String h = b64("{\"alg\":\"HS256\",\"typ\":\"JWT\"}");
        String p = b64("{\"sub\":\"" + sub + "\",\"role\":\"" + role + "\",\"jti\":\"t\","
                + "\"iat\":" + now + ",\"exp\":" + (now + ttlSec) + "}");
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(SECRET.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        String sig = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(mac.doFinal((h + "." + p).getBytes(StandardCharsets.UTF_8)));
        return h + "." + p + "." + sig;
    }

    @Test
    void validToken_passes() throws Exception {
        JwtVerifier v = new JwtVerifier(SECRET);
        Map<String, Object> claims = v.verify(sign("42", "USER", 900));
        assertThat(claims).isNotNull();
        assertThat(claims.get("sub")).isEqualTo("42");
    }

    @Test
    void wrongSecret_fails() throws Exception {
        JwtVerifier v = new JwtVerifier("other-secret-0000000000000000000000");
        assertThat(v.verify(sign("42", "USER", 900))).isNull();
    }

    @Test
    void expiredToken_fails() throws Exception {
        JwtVerifier v = new JwtVerifier(SECRET);
        assertThat(v.verify(sign("42", "USER", -10))).isNull();
    }

    @Test
    void refreshToken_rejected() throws Exception {
        JwtVerifier v = new JwtVerifier(SECRET);
        assertThat(v.verify(sign("42", "REFRESH", 900))).isNull();
    }

    @Test
    void garbage_fails() {
        JwtVerifier v = new JwtVerifier(SECRET);
        assertThat(v.verify("not.a.token")).isNull();
        assertThat(v.verify(null)).isNull();
        assertThat(v.verify("")).isNull();
    }

    @Test
    void emptySecret_openMode() {
        JwtVerifier v = new JwtVerifier("");
        assertThat(v.isEnabled()).isFalse();
        assertThat(new JwtVerifier(SECRET).isEnabled()).isTrue();
    }
}
