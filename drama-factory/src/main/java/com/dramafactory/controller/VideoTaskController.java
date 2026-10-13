package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.VideoTaskService;
import io.github.resilience4j.ratelimiter.RequestNotPermitted;
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.List;

@RestController
@RequestMapping("/api")
@Tag(name = "VideoTasks", description = "分镜视频任务的提交、查询与重试接口")
public class VideoTaskController {

    private final VideoTaskService videoTaskService;

    public VideoTaskController(VideoTaskService videoTaskService) {
        this.videoTaskService = videoTaskService;
    }

    /**
     * 提交单个分镜的视频任务。
     *
     * <p>受 {@code videoSubmit} 限流器保护；超过配额时走 {@link #submitRateLimited} 返回 429。</p>
     */
    @PostMapping("/shots/{shotId}/video-tasks")
    @RateLimiter(name = "videoSubmit", fallbackMethod = "submitRateLimited")
    @Operation(summary = "提交单个分镜的视频任务")
    public ResponseEntity<Records.VideoTaskResponse> submitForShot(@PathVariable Long shotId) {
        Records.SubmitOutcome outcome = videoTaskService.submit(shotId);
        HttpStatus status = outcome.created() ? HttpStatus.CREATED : HttpStatus.OK;
        return ResponseEntity.status(status).body(outcome.task());
    }

    /**
     * 批量提交某一集下所有分镜的视频任务。
     *
     * <p>受 {@code videoSubmit} 限流器保护；超过配额时走 {@link #submitAllRateLimited} 返回 429。</p>
     */
    @PostMapping("/episodes/{episodeId}/video-tasks/submit-all")
    @RateLimiter(name = "videoSubmit", fallbackMethod = "submitAllRateLimited")
    @Operation(summary = "批量提交剧集下全部分镜的视频任务")
    public ResponseEntity<List<Records.VideoTaskResponse>> submitAllForEpisode(@PathVariable Long episodeId) {
        List<Records.VideoTaskResponse> responses = videoTaskService.submitAllForEpisode(episodeId);
        return ResponseEntity.ok(responses);
    }

    @GetMapping("/shots/{shotId}/video-tasks")
    @Operation(summary = "查询分镜下的视频任务列表")
    public ResponseEntity<List<Records.VideoTaskResponse>> listByShot(@PathVariable Long shotId) {
        return ResponseEntity.ok(videoTaskService.listByShot(shotId));
    }

    @GetMapping("/video-tasks/{taskId}")
    @Operation(summary = "按 ID 查询视频任务")
    public ResponseEntity<Records.VideoTaskResponse> get(@PathVariable Long taskId) {
        return ResponseEntity.ok(videoTaskService.get(taskId));
    }

    @PostMapping("/video-tasks/{taskId}/retry")
    @Operation(summary = "重试视频任务")
    public ResponseEntity<Records.VideoTaskResponse> retry(@PathVariable Long taskId) {
        return ResponseEntity.ok(videoTaskService.retry(taskId));
    }

    /**
     * submitForShot 的限流兜底：被限流时返回 429。
     *
     * <p>注意：Resilience4j 的 fallback 方法要求与原方法返回类型一致，且最后一个参数为
     * 触发限流的异常类型。</p>
     */
    private ResponseEntity<Records.VideoTaskResponse> submitRateLimited(Long shotId, RequestNotPermitted ex) {
        return tooManyRequests();
    }

    /**
     * submitAllForEpisode 的限流兜底：被限流时返回 429。
     */
    private ResponseEntity<List<Records.VideoTaskResponse>> submitAllRateLimited(Long episodeId, RequestNotPermitted ex) {
        return tooManyRequests();
    }

    /**
     * 统一构造 429 响应体。
     *
     * <p>使用泛型 + unchecked 强转适配不同返回类型；由于两个 fallback 方法返回的具体类型
     * 与调用方期望一致，此处在类型安全上是受控的。</p>
     */
    @SuppressWarnings("unchecked")
    private <T> ResponseEntity<T> tooManyRequests() {
        Records.ErrorResponse body = new Records.ErrorResponse(
                429, "Too Many Requests", "视频任务提交过于频繁，请稍后再试",
                LocalDateTime.now(), MDC.get("request_id"));
        return ResponseEntity.status(429).header("Retry-After", "10").body((T) body);
    }
}

