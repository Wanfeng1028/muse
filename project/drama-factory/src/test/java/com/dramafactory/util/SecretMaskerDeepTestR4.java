package com.dramafactory.util;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SecretMaskerDeepTestR4 {

    @Test
    void mask_len8_returnsStars() {
        assertEquals("****", SecretMasker.mask("12345678"));
    }

    @Test
    void mask_len9_keepsEdges() {
        assertEquals("12****89", SecretMasker.mask("123456789"));
    }

    @Test
    void mask_len7_returnsStars() {
        assertEquals("****", SecretMasker.mask("1234567"));
    }

    @Test
    void mask_singleChar_returnsStars() {
        assertEquals("****", SecretMasker.mask("x"));
    }

    @Test
    void mask_chinese_keepsEdges() {
        assertEquals("密钥****AB", SecretMasker.mask("密钥字符串测试AB"));
    }

    @Test
    void maskBearer_lowercaseBearer() {
        assertEquals("Bearer ab****ij", SecretMasker.maskBearer("bearer abcdefghij"));
    }

    @Test
    void maskBearer_uppercaseBearer() {
        assertEquals("Bearer ab****ij", SecretMasker.maskBearer("BEARER abcdefghij"));
    }

    @Test
    void maskBearer_mixedCaseBearer() {
        assertEquals("Bearer ab****ij", SecretMasker.maskBearer("BeArEr abcdefghij"));
    }

    @Test
    void maskBearer_bearerOnly7Chars() {
        assertEquals("****", SecretMasker.maskBearer("Bearer "));
    }

    @Test
    void maskBearer_basicScheme() {
        assertEquals("Ba****Nz", SecretMasker.maskBearer("Basic dXNlcjpwYXNz"));
    }

    @Test
    void maskBearer_tokenWithSpaces() {
        assertEquals("Bearer ****", SecretMasker.maskBearer("Bearer   "));
    }

    @Test
    void mask_longToken_exact() {
        assertEquals("sk****ef", SecretMasker.mask("sk-1234567890abcdef"));
    }

    @Test
    void mask_whitespaceOnly() {
        assertEquals("****", SecretMasker.mask("   "));
    }

    @Test
    void mask_newlineInside() {
        assertEquals("ab****gh", SecretMasker.mask("ab\ncd\nef\ngh"));
    }
}