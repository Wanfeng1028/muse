package com.dramafactory.controller;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
@Tag(name = "健康检查", description = "服务健康检查接口")

public class HealthController {

    @GetMapping("/health")
    @Operation(summary = "查询服务健康状态")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }
}
