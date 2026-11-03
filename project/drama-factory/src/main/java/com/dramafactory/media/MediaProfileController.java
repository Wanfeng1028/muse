package com.dramafactory.media;

import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.dramafactory.exception.ResourceNotFoundException;

import java.util.List;

/**
 * 媒体预设 REST 控制器，提供平台媒体预设的查询接口。
 */
@RestController
@RequestMapping("/api/media-profiles")
@Tag(name = "MediaProfiles", description = "平台媒体预设")
public class MediaProfileController {

    private final MediaProfileService mediaProfileService;

    public MediaProfileController(MediaProfileService mediaProfileService) {
        this.mediaProfileService = mediaProfileService;
    }

    /**
     * 获取媒体预设列表，可按平台前缀过滤。
     *
     * @param platform 可选的平台前缀
     * @return 媒体预设列表
     */
    @GetMapping("")
    public List<MediaProfile> list(@RequestParam(required = false) String platform) {
        if (platform != null && !platform.isEmpty()) {
            return mediaProfileService.forPlatform(platform);
        }
        return mediaProfileService.list();
    }

    /**
     * 按名称获取媒体预设。
     *
     * @param name 预设名称
     * @return 对应的媒体预设
     */
    @GetMapping("/{name}")
    public MediaProfile get(@PathVariable String name) {
        try {
            return mediaProfileService.get(name);
        } catch (IllegalArgumentException e) {
            throw ResourceNotFoundException.withKey("MediaProfile", name);
        }
    }
}
