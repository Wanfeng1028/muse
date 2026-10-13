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

@RestController
@RequestMapping("/api")
public class VideoTaskController {

    private final VideoTaskService videoTaskService;

    public VideoTaskController(VideoTaskService videoTaskService) {
        this.videoTaskService = videoTaskService;
    }

    @PostMapping("/shots/{shotId}/video-tasks")
    public ResponseEntity<Records.VideoTaskResponse> submitForShot(@PathVariable Long shotId) {
        Records.SubmitOutcome outcome = videoTaskService.submit(shotId);
        HttpStatus status = outcome.created() ? HttpStatus.CREATED : HttpStatus.OK;
        return ResponseEntity.status(status).body(outcome.task());
    }

    @PostMapping("/episodes/{episodeId}/video-tasks/submit-all")
    public ResponseEntity<List<Records.VideoTaskResponse>> submitAllForEpisode(@PathVariable Long episodeId) {
        List<Records.VideoTaskResponse> responses = videoTaskService.submitAllForEpisode(episodeId);
        return ResponseEntity.ok(responses);
    }

    @GetMapping("/shots/{shotId}/video-tasks")
    public ResponseEntity<List<Records.VideoTaskResponse>> listByShot(@PathVariable Long shotId) {
        return ResponseEntity.ok(videoTaskService.listByShot(shotId));
    }

    @GetMapping("/video-tasks/{taskId}")
    public ResponseEntity<Records.VideoTaskResponse> get(@PathVariable Long taskId) {
        return ResponseEntity.ok(videoTaskService.get(taskId));
    }

    @PostMapping("/video-tasks/{taskId}/retry")
    public ResponseEntity<Records.VideoTaskResponse> retry(@PathVariable Long taskId) {
        return ResponseEntity.ok(videoTaskService.retry(taskId));
    }
}
