package com.dramaauth.service;

import org.springframework.stereotype.Service;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

/**
 * 密码哈希服务。
 *
 * <p>说明：离线构建仓库无 spring-security（无 BCrypt），此处采用 JDK 标准库的
 * PBKDF2-HMAC-SHA256，600,000 轮迭代（OWASP 2023+ 推荐参数），16 字节随机盐，
 * 与 BCrypt 同等安全级别。格式：{@code pbkdf2$600000$<saltB64>$<hashB64>}。
 * 密码原文永不落盘、不打日志。
 */
@Service
public class PasswordService {

    private static final int ITERATIONS = 600_000;
    private static final int SALT_BYTES = 16;
    private static final int HASH_BYTES = 32;

    private final SecureRandom random = new SecureRandom();

    /** 生成 hash */
    public String hash(String rawPassword) {
        byte[] salt = new byte[SALT_BYTES];
        random.nextBytes(salt);
        byte[] hash = pbkdf2(rawPassword.toCharArray(), salt, ITERATIONS);
        return "pbkdf2$" + ITERATIONS + "$"
                + Base64.getEncoder().encodeToString(salt) + "$"
                + Base64.getEncoder().encodeToString(hash);
    }

    /** 校验；格式不对或异常一律返回 false（不抛异常防枚举） */
    public boolean matches(String rawPassword, String stored) {
        try {
            if (rawPassword == null || stored == null) {
                return false;
            }
            String[] parts = stored.split("\\$");
            if (parts.length != 4 || !"pbkdf2".equals(parts[0])) {
                return false;
            }
            int iters = Integer.parseInt(parts[1]);
            byte[] salt = Base64.getDecoder().decode(parts[2]);
            byte[] expected = Base64.getDecoder().decode(parts[3]);
            byte[] actual = pbkdf2(rawPassword.toCharArray(), salt, iters);
            return MessageDigest.isEqual(expected, actual);
        } catch (Exception e) {
            return false;
        }
    }

    private byte[] pbkdf2(char[] password, byte[] salt, int iterations) {
        try {
            PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, HASH_BYTES * 8);
            SecretKeyFactory factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
            byte[] result = factory.generateSecret(spec).getEncoded();
            spec.clearPassword();
            return result;
        } catch (Exception e) {
            throw new IllegalStateException("PBKDF2 计算失败", e);
        }
    }
}
