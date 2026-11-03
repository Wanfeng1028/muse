package com.dramafactory.util;

/**
 * 敏感字符串脱敏工具。纯静态、无外部依赖。
 *
 * <p>约定：
 * <ul>
 *   <li>{@link #mask(String)}：null/空原样返回；长度 ≤8 返回 {@code "****"}；否则保留前 2 + {@code "****"} + 后 2。</li>
 *   <li>{@link #maskBearer(String)}：形如 {@code "Bearer xxx"} 时脱敏后半段，否则走 {@link #mask(String)}。</li>
 * </ul>
 *
 * <p>用于日志/展示场景，替代直接打印密钥或完整 Authorization 头。
 */
public final class SecretMasker {

    private static final String MASK = "****";
    private static final String BEARER_PREFIX = "Bearer ";

    private SecretMasker() {
    }

    /**
     * 脱敏一段密钥。
     *
     * @param secret 原始值，可为 null
     * @return 脱敏后的字符串；null/空原样返回
     */
    public static String mask(String secret) {
        if (secret == null || secret.isEmpty()) {
            return secret;
        }
        if (secret.length() <= 8) {
            return MASK;
        }
        return secret.substring(0, 2) + MASK + secret.substring(secret.length() - 2);
    }

    /**
     * 脱敏 Authorization 头。仅处理 {@code "Bearer "} 前缀，大小写不敏感。
     *
     * @param headerValue Authorization 头的值，可为 null
     * @return Bearer 形式返回 {@code "Bearer " + mask(token)}；否则返回 {@link #mask(String)}
     */
    public static String maskBearer(String headerValue) {
        if (headerValue == null) {
            return null;
        }
        if (headerValue.length() > BEARER_PREFIX.length()
                && headerValue.regionMatches(true, 0, BEARER_PREFIX, 0, BEARER_PREFIX.length())) {
            String token = headerValue.substring(BEARER_PREFIX.length());
            return BEARER_PREFIX + mask(token);
        }
        return mask(headerValue);
    }
}
