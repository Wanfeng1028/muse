package com.dramaauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 账号微服务启动类。
 * JWT 密钥缺失时由 JwtService 在启动期拒绝启动。
 */
@SpringBootApplication
public class DramaAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(DramaAuthApplication.class, args);
    }
}
