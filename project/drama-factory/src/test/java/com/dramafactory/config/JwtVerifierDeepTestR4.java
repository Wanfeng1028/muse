package com.dramafactory.config;

import org.junit.jupiter.api.Test;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JwtVerifierDeepTestR4 {

    private static final String SECRET = "r4-test-secret-abcdef";

    private static String b64url(String s) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(s.getBytes(StandardCharsets.UTF_8));
    }

    private static String sign(String secret, String headerB64, String payloadB64) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        byte[] sig = mac.doFinal((headerB64 + "." + payloadB64).getBytes(StandardCharsets.UTF_8));
        return Base64.getUrlEncoder().withoutPadding().encodeToString(sig);
    }

    private static String token(String secret, String payloadJson) throws Exception {
        String h = b64url("{\"alg\":\"HS256\",\"typ\":\"JWT\"}");
        String p = b64url(payloadJson);
        return h + "." + p + "." + sign(secret, h, p);
    }

    @Test
    void verify_noExp_rejected() throws Exception {
        JwtVerifier verifier = new JwtVerifier(SECRET);
        String t = token(SECRET, "{\"sub\":\"u1\"}");
        assertNull(verifier.verify(t));
    }

    @Test
    void verify_expAsString_rejected() throws Exception {
        JwtVerifier verifier = new JwtVerifier(SECRET);
        String t = token(SECRET, "{\"exp\":\"9999999999\"}");
        assertNull(verifier.verify(t));
    }

    @Test
    void verify_expEqualsNow_rejected() throws Exception {
        JwtVerifier verifier = new JwtVerifier(SECRET);
        long nowSec = System.currentTimeMillis() / 1000;
        String t = token(SECRET, "{\"exp\":" + (nowSec - 1) + "}");
        assertNull(verifier.verify(t));
    }

    @Test
    void verify_roleLowercaseRefresh_passes() throws Exception {
        JwtVerifier verifier = new JwtVerifier(SECRET);
        long future = System.currentTimeMillis() / 1000 + 3600;
        String t = token(SECRET, "{\"exp\":" + future + ",\"role\":\"refresh\"}");
        Map<String, Object> claims = verifier.verify(t);
        assertNotNull(claims);
        assertEquals("refresh", claims.get("role"));
    }

    @Test
    void verify_twoSegments_rejected() {
        JwtVerifier verifier = new JwtVerifier(SECRET);
        assertNull(verifier.verify("a.b"));
    }

    @Test
    void verify_fourSegments_rejected() {
        JwtVerifier verifier = new JwtVerifier(SECRET);
        assertNull(verifier.verify("a.b.c.d"));
    }

    @Test
    void verify_tamperedPayload_rejected() throws Exception {
        JwtVerifier verifier = new JwtVerifier(SECRET);
        long future = System.currentTimeMillis() / 1000 + 3600;
        String t = token(SECRET, "{\"exp\":" + future + "}");
        String[] parts = t.split("\\.");
        String payload = parts[1];
        char last = payload.charAt(payload.length() - 1);
        char replaced = last == 'A' ? 'B' : 'A';
        String tampered = payload.substring(0, payload.length() - 1) + replaced;
        String bad = parts[0] + "." + tampered + "." + parts[2];
        assertNull(verifier.verify(bad));
    }

    @Test
    void verify_tamperedSignature_rejected() throws Exception {
        JwtVerifier verifier = new JwtVerifier(SECRET);
        long future = System.currentTimeMillis() / 1000 + 3600;
        String t = token(SECRET, "{\"exp\":" + future + "}");
        String[] parts = t.split("\\.");
        String sig = parts[2];
        char last = sig.charAt(sig.length() - 1);
        char replaced = last == 'A' ? 'B' : 'A';
        String tampered = sig.substring(0, sig.length() - 1) + replaced;
        String bad = parts[0] + "." + parts[1] + "." + tampered;
        assertNull(verifier.verify(bad));
    }

    @Test
    void verify_payloadNotJson_rejected() throws Exception {
        JwtVerifier verifier = new JwtVerifier(SECRET);
        String h = b64url("{\"alg\":\"HS256\",\"typ\":\"JWT\"}");
        String p = b64url("not-json{{{");
        String t = h + "." + p + "." + sign(SECRET, h, p);
        assertNull(verifier.verify(t));
    }

    @Test
    void verify_emptyString_rejected() {
        JwtVerifier verifier = new JwtVerifier(SECRET);
        assertNull(verifier.verify(""));
    }

    @Test
    void isEnabled_blankSecret_false() {
        JwtVerifier verifier = new JwtVerifier("   ");
        assertFalse(verifier.isEnabled());
    }

    @Test
    void isEnabled_normalSecret_true() {
        JwtVerifier verifier = new JwtVerifier("s");
        assertTrue(verifier.isEnabled());
    }

    @Test
    void verify_nullSecret_verifier_rejects() {
        JwtVerifier verifier = new JwtVerifier(null);
        assertNull(verifier.verify("a.b.c"));
    }

    @Test
    void verify_claimsContainSub() throws Exception {
        JwtVerifier verifier = new JwtVerifier(SECRET);
        long future = System.currentTimeMillis() / 1000 + 3600;
        String t = token(SECRET, "{\"sub\":\"u42\",\"exp\":" + future + "}");
        Map<String, Object> claims = verifier.verify(t);
        assertNotNull(claims);
        assertEquals("u42", claims.get("sub"));
    }
}