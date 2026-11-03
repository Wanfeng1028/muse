package com.dramafactory.util;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

/**
 * SecretMasker 纯单测，不启动 Spring 上下文。
 */
class SecretMaskerTest {

    @Test
    void mask_null_returnsNull() {
        assertNull(SecretMasker.mask(null));
    }

    @Test
    void mask_empty_returnsEmpty() {
        assertEquals("", SecretMasker.mask(""));
    }

    @Test
    void mask_short_returnsStars() {
        assertEquals("****", SecretMasker.mask("abc"));
        assertEquals("****", SecretMasker.mask("12345678")); // 边界：长度 8
    }

    @Test
    void mask_long_keepsEdges() {
        // 边界：长度 9
        assertEquals("12****89", SecretMasker.mask("123456789"));
        assertEquals("sk****yz", SecretMasker.mask("sk-abcdefghij-yz"));
    }

    @Test
    void maskBearer_bearerPrefix_masksToken() {
        assertEquals("Bearer 12****89", SecretMasker.maskBearer("Bearer 123456789"));
    }

    @Test
    void maskBearer_bearerPrefixCaseInsensitive() {
        assertEquals("Bearer 12****89", SecretMasker.maskBearer("bearer 123456789"));
    }

    @Test
    void maskBearer_shortToken() {
        assertEquals("Bearer ****", SecretMasker.maskBearer("Bearer abc"));
    }

    @Test
    void maskBearer_nonBearer_fallsBackToMask() {
        assertEquals("12****89", SecretMasker.maskBearer("123456789"));
        assertEquals("****", SecretMasker.maskBearer("abc"));
    }

    @Test
    void maskBearer_null_returnsNull() {
        assertNull(SecretMasker.maskBearer(null));
    }

    @Test
    void maskBearer_bareBearerNoToken_fallsBackToMask() {
        // "Bearer " 长 7（≤8），走 mask() 直接返回 "****"
        assertEquals("****", SecretMasker.maskBearer("Bearer "));
    }
}
