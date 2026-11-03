package com.scaffold.system.domain.vo;

public record LoginResponse(String token, long expiresIn) {
}
