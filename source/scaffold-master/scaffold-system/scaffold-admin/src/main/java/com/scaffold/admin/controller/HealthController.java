package com.scaffold.admin.controller;

import com.scaffold.common.domain.R;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.OffsetDateTime;
import java.util.Map;

@RestController
@RequestMapping("/api")
public class HealthController {

    @GetMapping("/health")
    public R<Map<String, Object>> health() {
        return R.success(Map.of(
                "status", "UP",
                "time", OffsetDateTime.now().toString()
        ));
    }
}
