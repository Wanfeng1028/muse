package com.dramafactory.controller;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.VideoTask;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.FfmpegService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * 媒体文件访问控制器，负责视频文件的安全读取与返回。
 * 通过路径校验防止路径穿越攻击。
 */
@RestController
@RequestMapping("/media")
public class MediaController {

    /** 媒体文件存储根目录，可通过配置项 drama.storage 覆盖 */
    private final String storageDir;

    /** 视频任务仓储 */
    private final VideoTaskRepository videoTaskRepository;

    /** 成片仓储 */
    private final FinalCutRepository finalCutRepository;

    /** ffmpeg 服务，用于抽取海报帧 */
    private final FfmpegService ffmpegService;

    /**
     * 构造器注入依赖。
     *
     * @param storageDir          媒体存储根目录
     * @param videoTaskRepository 视频任务仓储
     * @param finalCutRepository  成片仓储
     */
    public MediaController(@Value("${drama.storage:./data/media}") String storageDir,
                           VideoTaskRepository videoTaskRepository,
                           FinalCutRepository finalCutRepository,
                           FfmpegService ffmpegService) {
        this.storageDir = storageDir;
        this.videoTaskRepository = videoTaskRepository;
        this.finalCutRepository = finalCutRepository;
        this.ffmpegService = ffmpegService;
    }

    /**
     * 获取指定视频任务生成的视频文件。
     *
     * @param taskId 视频任务 ID
     * @return 视频资源响应
     */
    @GetMapping("/videos/{taskId}")
    public ResponseEntity<Resource> getVideo(@PathVariable Long taskId) {
        // 查询视频任务，不存在则抛出异常
        VideoTask task = videoTaskRepository.findById(taskId)
                .orElseThrow(() -> new ResourceNotFoundException("VideoTask", taskId));

        // 加载并校验文件路径安全性
        Resource resource = loadSafe(task.getLocalPath());

        // 校验文件是否存在
        if (!resource.exists() || !resource.isReadable()) {
            throw new ResourceNotFoundException("VideoTask", taskId);
        }

        // 构造响应，Content-Type 为 video/mp4，采用 inline 方式展示
        MediaType mediaType = MediaType.parseMediaType("video/mp4");
        return ResponseEntity.ok()
                .contentType(mediaType)
                .header(HttpHeaders.CONTENT_DISPOSITION, "inline")
                .body(resource);
    }

    /**
     * 获取指定成片的视频文件。
     *
     * @param id 成片 ID
     * @return 视频资源响应
     */
    @GetMapping("/finals/{id}")
    public ResponseEntity<Resource> getFinal(@PathVariable Long id) {
        // 查询成片，不存在则抛出异常
        FinalCut finalCut = finalCutRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("FinalCut", id));

        // 加载并校验文件路径安全性
        Resource resource = loadSafe(finalCut.getFilePath());

        // 校验文件是否存在
        if (!resource.exists() || !resource.isReadable()) {
            throw new ResourceNotFoundException("FinalCut", id);
        }

        // 构造响应，Content-Type 为 video/mp4，采用 inline 方式展示
        MediaType mediaType = MediaType.parseMediaType("video/mp4");
        return ResponseEntity.ok()
                .contentType(mediaType)
                .header(HttpHeaders.CONTENT_DISPOSITION, "inline")
                .body(resource);
    }

    /**
     * 安全加载文件资源，防止路径穿越。
     * 配置路径与目标路径均转为绝对路径并规范化，校验目标路径必须位于存储根目录下。
     *
     * @param configuredPath 数据库中配置的文件路径
     * @return 文件系统资源
     */
    private Resource loadSafe(String configuredPath) {
        // 计算存储根目录的绝对规范路径
        Path base = Paths.get(storageDir).toAbsolutePath().normalize();
        // 计算目标文件的绝对规范路径
        Path target = Paths.get(configuredPath).toAbsolutePath().normalize();

        // 校验目标路径必须位于存储根目录之下，否则视为非法路径
        if (!target.startsWith(base)) {
            throw new SecurityException("非法文件路径");
        }

        return new FileSystemResource(target);
    }

    /**
     * 获取指定成片的海报帧（JPEG）。
     * <p>从成片视频第 1 秒处抽取一帧，结果缓存为 {@code <filePath>.poster.jpg}，
     * 缓存命中时直接返回，不重复抽取。</p>
     *
     * @param id 成片 ID
     * @return 海报图片资源响应
     */
    @GetMapping("/finals/{id}/poster.jpg")
    public ResponseEntity<Resource> getFinalPoster(@PathVariable Long id) {
        FinalCut finalCut = finalCutRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("FinalCut", id));

        Path videoPath = Paths.get(finalCut.getFilePath());
        Path posterPath = Paths.get(finalCut.getFilePath() + ".poster.jpg");

        if (!Files.exists(posterPath) || !Files.isRegularFile(posterPath)) {
            try {
                ffmpegService.extractPoster(videoPath, posterPath);
            } catch (Exception ex) {
                throw new ResourceNotFoundException("FinalCut", id);
            }
        }

        Resource resource = loadSafe(posterPath.toString());
        if (!resource.exists() || !resource.isReadable()) {
            throw new ResourceNotFoundException("FinalCut", id);
        }

        return ResponseEntity.ok()
                .contentType(MediaType.IMAGE_JPEG)
                .header(HttpHeaders.CONTENT_DISPOSITION, "inline; filename=\"poster.jpg\"")
                .body(resource);
    }
}
