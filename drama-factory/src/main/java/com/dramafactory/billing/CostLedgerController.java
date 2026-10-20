package com.dramafactory.billing;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 成本账本只读查询接口。
 */
@RestController
@RequestMapping("/api/cost-ledger")
public class CostLedgerController {

    private final CostLedgerService service;
    private final CostLedgerEntryRepository repository;

    public CostLedgerController(CostLedgerService service, CostLedgerEntryRepository repository) {
        this.service = service;
        this.repository = repository;
    }

    /**
     * 汇总成本。from/to 为 ISO LocalDateTime（如 2026-10-19T00:00:00），缺省表示不过滤。
     */
    @GetMapping("/summary")
    public CostSummary summary(
            @RequestParam(name = "projectId", required = false) Long projectId,
            @RequestParam(name = "provider", required = false) String provider,
            @RequestParam(name = "from", required = false) String from,
            @RequestParam(name = "to", required = false) String to) {
        LocalDateTime fromTime = parseTime(from);
        LocalDateTime toTime = parseTime(to);
        return service.summarize(projectId, provider, fromTime, toTime);
    }

    /**
     * 按天汇总各提供方费用。date 格式 yyyy-MM-dd，缺省为今天；非法返回 400。
     */
    @GetMapping("/daily")
    public List<CostLedgerService.ProviderDailyCost> daily(
            @RequestParam(name = "date", required = false) String date) {
        LocalDate day = parseDate(date);
        return service.summarizeDaily(day);
    }

    /**
     * 按天汇总费用趋势。days 缺省为 14；非数字返回 400；超出 [1, 90] 由 service 钳制。
     */
    @GetMapping("/trend")
    public List<CostLedgerService.DailyTrendPoint> trend(
            @RequestParam(name = "days", required = false) String days) {
        int parsed = parseDays(days);
        return service.summarizeTrend(parsed);
    }

    private static int parseDays(String value) {
        if (value == null || value.isBlank()) {
            return 14;
        }
        try {
            return Integer.parseInt(value.trim());
        } catch (NumberFormatException e) {
            throw new BadRequestError("Invalid days: " + value);
        }
    }

    private static LocalDate parseDate(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return LocalDate.parse(value.trim());
        } catch (DateTimeParseException e) {
            throw new BadRequestError("Invalid date: " + value);
        }
    }

    /**
     * 预算总览：总预算/已花费/冻结中/可用/使用率/模式/开关。
     */
    @GetMapping("/budget")
    public CostLedgerService.BudgetStatus budget() {
        return service.budgetStatus();
    }

    /**
     * 查询账本条目。status 为枚举名，非法值返回 400。
     */
    @GetMapping("/entries")
    public List<CostLedgerEntry> entries(
            @RequestParam(name = "projectId", required = false) Long projectId,
            @RequestParam(name = "provider", required = false) String provider,
            @RequestParam(name = "status", required = false) String status,
            @RequestParam(name = "from", required = false) String from,
            @RequestParam(name = "to", required = false) String to,
            @RequestParam(name = "limit", required = false) String limit) {
        LocalDateTime fromTime = parseTime(from);
        LocalDateTime toTime = parseTime(to);
        CostLedgerStatus statusEnum = parseStatus(status);
        int max = parseLimit(limit);

        List<CostLedgerEntry> candidates;
        if (projectId != null) {
            candidates = repository.findByProjectId(projectId);
        } else if (provider != null) {
            candidates = repository.findByProvider(provider);
        } else if (statusEnum != null) {
            candidates = repository.findByStatus(statusEnum);
        } else {
            candidates = repository.findAll();
        }
        List<CostLedgerEntry> result = new ArrayList<>();
        for (CostLedgerEntry entry : candidates) {
            if (provider != null && !provider.equals(entry.getProvider())) {
                continue;
            }
            if (statusEnum != null && entry.getStatus() != statusEnum) {
                continue;
            }
            if (fromTime != null && (entry.getCreatedAt() == null || entry.getCreatedAt().isBefore(fromTime))) {
                continue;
            }
            if (toTime != null && (entry.getCreatedAt() == null || entry.getCreatedAt().isAfter(toTime))) {
                continue;
            }
            result.add(entry);
        }
        if (result.size() > max) {
            return result.subList(0, max);
        }
        return result;
    }

    private static int parseLimit(String value) {
        if (value == null || value.isBlank()) {
            return 100;
        }
        int parsed;
        try {
            parsed = Integer.parseInt(value.trim());
        } catch (NumberFormatException e) {
            throw new BadRequestError("Invalid limit: " + value);
        }
        if (parsed <= 0) {
            throw new BadRequestError("Invalid limit: " + value);
        }
        return Math.min(parsed, 500);
    }

    private static LocalDateTime parseTime(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return LocalDateTime.parse(value.trim());
        } catch (DateTimeParseException ex) {
            throw new BadRequestError("Invalid datetime: " + value);
        }
    }

    private static CostLedgerStatus parseStatus(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return CostLedgerStatus.valueOf(value.trim().toUpperCase());
        } catch (IllegalArgumentException ex) {
            throw new BadRequestError("Invalid status: " + value);
        }
    }

    /**
     * 仅处理本控制器的 400 错误，返回 JSON {"error": "..."}。
     */
    @ExceptionHandler(BadRequestError.class)
    public ResponseEntity<Map<String, String>> handleBadRequest(BadRequestError ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("error", ex.getMessage()));
    }

    /**
     * 控制器内部的 400 异常类型。
     */
    public static class BadRequestError extends RuntimeException {
        public BadRequestError(String message) {
            super(message);
        }
    }
}
