package com.dramafactory.service;

import com.dramafactory.dto.canvas.CanvasJobV2;
import com.dramafactory.exception.ResourceNotFoundException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

@Service
public class CanvasJobService {

    private final CanvasEventService canvasEventService;
    private final CanvasProjectService canvasProjectService;
    private final long jobDelayMs;
    private final ScheduledExecutorService executor = Executors.newSingleThreadScheduledExecutor();
    private final ConcurrentHashMap<String, CanvasJobV2> jobs = new ConcurrentHashMap<>();

    public CanvasJobService(CanvasEventService canvasEventService,
                            @Lazy CanvasProjectService canvasProjectService,
                            @Value("${drama.canvas.job-delay-ms:3000}") long jobDelayMs) {
        this.canvasEventService = canvasEventService;
        this.canvasProjectService = canvasProjectService;
        this.jobDelayMs = jobDelayMs;
    }

    public CanvasJobV2 createJob(String nodeId) {
        String jobId = "job-" + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        int version = canvasProjectService.currentVersion();
        String now = OffsetDateTime.now().toString();
        CanvasJobV2 job = new CanvasJobV2(jobId, nodeId, "running", version, now, now);
        jobs.put(jobId, job);

        Map<String, Object> runningData = new LinkedHashMap<>();
        runningData.put("job_id", jobId);
        runningData.put("node_id", nodeId);
        runningData.put("status", "running");
        runningData.put("version", version);
        canvasEventService.broadcast("job.status", runningData);

        executor.schedule(() -> completeJob(jobId, nodeId), jobDelayMs, TimeUnit.MILLISECONDS);
        return job;
    }

    private void completeJob(String jobId, String nodeId) {
        int newVersion = canvasProjectService.currentVersion();
        if (nodeId != null && !nodeId.isEmpty()) {
            newVersion = canvasProjectService.markNodeDone(nodeId, "job");
        }
        CanvasJobV2 existing = jobs.get(jobId);
        if (existing == null) {
            throw new ResourceNotFoundException("job", 0L);
        }
        CanvasJobV2 done = new CanvasJobV2(jobId, nodeId, "done", newVersion, existing.createdAt(), OffsetDateTime.now().toString());
        jobs.put(jobId, done);

        Map<String, Object> doneData = new LinkedHashMap<>();
        doneData.put("job_id", jobId);
        doneData.put("node_id", nodeId);
        doneData.put("status", "done");
        doneData.put("version", newVersion);
        canvasEventService.broadcast("job.status", doneData);

        Map<String, Object> changed = new LinkedHashMap<>();
        changed.put("version", newVersion);
        changed.put("updated_by", "job");
        changed.put("kind", "job");
        canvasEventService.broadcast("canvas.changed", changed);
    }

    public CanvasJobV2 getJob(String jobId) {
        CanvasJobV2 job = jobs.get(jobId);
        if (job == null) {
            throw new ResourceNotFoundException("job", 0L);
        }
        return job;
    }
}
