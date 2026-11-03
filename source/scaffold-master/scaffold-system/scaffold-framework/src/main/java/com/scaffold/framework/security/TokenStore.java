package com.scaffold.framework.security;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.util.Optional;
import java.util.concurrent.TimeUnit;

@Service
public class TokenStore {

    private static final String TOKEN_KEY_PREFIX = "auth:token:";

    private final StringRedisTemplate redisTemplate;

    public TokenStore(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public void store(String token, String username, long expiresSeconds) {
        redisTemplate.opsForValue().set(key(token), username, expiresSeconds, TimeUnit.SECONDS);
    }

    public Optional<String> usernameOf(String token) {
        return Optional.ofNullable(redisTemplate.opsForValue().get(key(token)));
    }

    public void revoke(String token) {
        redisTemplate.delete(key(token));
    }

    private String key(String token) {
        return TOKEN_KEY_PREFIX + token;
    }
}
