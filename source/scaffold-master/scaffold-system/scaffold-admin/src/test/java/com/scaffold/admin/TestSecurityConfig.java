package com.scaffold.admin;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@TestConfiguration
public class TestSecurityConfig {

    @Bean
    @Order(0)
    public SecurityFilterChain testEndpointsFilterChain(HttpSecurity http) throws Exception {
        http
                .securityMatcher("/api/test/**")
                .csrf(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(registry -> registry.anyRequest().permitAll());
        return http.build();
    }
}
