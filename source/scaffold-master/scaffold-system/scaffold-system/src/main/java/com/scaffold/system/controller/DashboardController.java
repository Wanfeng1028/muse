package com.scaffold.system.controller;

import com.scaffold.common.domain.R;
import com.scaffold.system.service.DashboardService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/dashboard")
public class DashboardController {

    private final DashboardService service;

    public DashboardController(DashboardService service) {
        this.service = service;
    }

    @GetMapping("/summary")
    public R<Map<String, Object>> summary(@RequestParam(required = false, defaultValue = "24h") String range) {
        return R.success(service.summary(range));
    }
}
