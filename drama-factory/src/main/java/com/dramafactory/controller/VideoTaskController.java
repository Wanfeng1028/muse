package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.VideoTaskService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 视频生成任务控制器。
 * 提供分镜视频任务的提交、查询与重试接口。
 */
@RestController
@RequestMapping("/api")
public class VideoTaskController {

    private final VideoTaskService videoTaskService;

    /**
     * 构造器注入 VideoTaskService。
     *
     * @param videoTaskService 视频任务业务服务
     */
    public VideoTaskController(VideoTaskService videoTaskService) {
        this.videoTaskService = videoTaskService;
    }

    /**
     * 提交单个分镜的视频生成任务。
     *
     * @param shotId 分镜 ID
     * @return 创建成功的视频任务响应，HTTP 201
     */
    @PostMapping("/shots/{shotId}/video-tasks")
    public ResponseEntity<Records.VideoTaskResponse> submitForShot(@PathVariable Long shotId) {
        Records.VideoTaskResponse response = videoTaskService.submit(shotId);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    /**
     * 为该剧集下所有分镜批量提交视频生成任务。
     *
     * @param episodeId 剧集 ID
     * @return 批量提交的视频任务响应列表，HTTP 200
     */
    @PostMapping("/episodes/{episodeId}/video-tasks/submit-all")
    public ResponseEntity<List<Records.VideoTaskResponse>> submitAllForEpisode(@PathVariable Long episodeId) {
        List<Records.VideoTaskResponse> responses = videoTaskService.submitAllForEpisode(episodeId);
        return ResponseEntity.ok(responses);
    }

    /**
     * 查询指定分镜下的所有视频任务。
     *
     * @param shotId 分镜 ID
     * @return 视频任务响应列表
     */
    @GetMapping("/shots/{shotId}/video-tasks")
    public List<Records.VideoTaskResponse> listByShot(@PathVariable Long shotId) {
        return videoTaskService.listByShot(shotId);
    }

    /**
     * 根据任务 ID 查询视频任务详情。
     *
     * @param id 视频任务 ID
     * @return 视频任务响应
     */
    @GetMapping("/video-tasks/{id}")
    public Records.VideoTaskResponse getById(@PathVariable Long id) {
        return videoTaskService.get(id);
    }

    /**
     * 重试失败的视频任务。
     *
     * @param id 视频任务 ID
     * @return 重试后的视频任务响应，HTTP 200
     */
    @PostMapping("/video-tasks/{id}/retry")
    public ResponseEntity<Records.VideoTaskResponse> retry(@PathVariable Long id) {
        Records.VideoTaskResponse response = videoTaskService.retry(id);
        return ResponseEntity.ok(response);
    }
}
