
package com.dramafactory.controller;

import com.dramafactory.service.UsageService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

/**
 * Token / 成本用量统计聚合 API。
 */
@RestController
@RequestMapping("/api/usage")
@Tag(name = "Usage", description = "Token 与成本用量统计接口")
public class UsageController {

    private final UsageService usageService;

    public UsageController(UsageService usageService) {
        this.usageService = usageService;
    }

    /** 总量汇总。 */
    @GetMapping("/summary")
    @Operation(summary = "用量汇总（支持 provider/model/days 过滤）")
    public SummaryDto summary(@RequestParam(required = false) String provider,
                              @RequestParam(required = false) String model,
                              @RequestParam(required = false, defaultValue = "0") int days) {
        UsageService.UsageSummary s = usageService.summary(provider, model, days);
        return new SummaryDto(s.tokensTotal(), s.costCentsTotal(), s.taskCount(), s.runCount(),
                s.stepCount(), s.requestCount());
    }

    /** 按模型 / Agent 类型聚合。 */
    @GetMapping("/by-model")
    @Operation(summary = "按模型聚合用量")
    public List<ModelDto> byModel() {
        return usageService.byModel().stream()
                .map(m -> new ModelDto(m.model(), m.tokens(), m.costCents(), m.taskCount()))
                .toList();
    }

    /** 按天聚合，默认 30 天。 */
    @GetMapping("/by-day")
    @Operation(summary = "按天聚合用量（支持 provider/model 过滤）")
    public List<DayDto> byDay(@RequestParam(name = "days", defaultValue = "30") int days,
                              @RequestParam(required = false) String provider,
                              @RequestParam(required = false) String model) {
        return usageService.byDay(days, provider, model).stream()
                .map(d -> new DayDto(d.date(), d.tokens(), d.costCents(), d.videoCount(), d.stepCount()))
                .toList();
    }

    /** 按 Run 聚合，默认 20 条。 */
    @GetMapping("/requests")
@Operation(summary = "逐请求用量明细（合并 VideoTask 与 AgentStep）")
public List<RequestDto> requests(@RequestParam(defaultValue = "50") int limit,
                                 @RequestParam(required = false) String provider,
                                 @RequestParam(required = false) String model,
                                 @RequestParam(defaultValue = "30") int days) {
    return usageService.requests(limit, provider, model, days).stream()
            .map(r -> new RequestDto(r.id(), r.kind(), r.time(), r.provider(), r.model(),
                    r.tokensUsed(), r.costCents(), r.costEstimated(), r.latencyMs(), r.status()))
            .toList();
}

@GetMapping("/filters")
@Operation(summary = "筛选器下拉数据（providers / models）")
public UsageService.FilterOptions filters() {
    return usageService.filters();
}

@GetMapping("/by-run")
    @Operation(summary = "按运行记录聚合用量")
    public List<RunDto> byRun(@RequestParam(name = "limit", defaultValue = "20") int limit) {
        return usageService.byRun(limit).stream()
                .map(r -> new RunDto(r.runId(), r.goal(), r.tokens(), r.costCents(), r.createdAt()))
                .toList();
    }

    // ==== 返回 DTO ====

    /** 总量汇总 DTO。 */
    public record SummaryDto(Long tokensTotal, Long costCentsTotal, long taskCount, long runCount,
                         long stepCount, long requestCount) {}

    /** 按模型/Agent 类型聚合 DTO。 */
    public record ModelDto(String model, Long tokens, Long costCents, long taskCount) {}

    /** 按天聚合 DTO。 */
    public record DayDto(LocalDate date, Long tokens, Long costCents, long videoCount, long stepCount) {}

    /** 按 Run 聚合 DTO。 */
    public record RunDto(Long runId, String goal, Long tokens, Long costCents, LocalDateTime createdAt) {}

public record RequestDto(Long id, String kind, LocalDateTime time, String provider, String model,
                         Long tokensUsed, Long costCents, Boolean costEstimated,
                         Long latencyMs, String status) {}
}
