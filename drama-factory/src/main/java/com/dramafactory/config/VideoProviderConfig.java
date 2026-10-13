package com.dramafactory.config;

import com.dramafactory.service.video.VideoProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 视频提供者装配配置。
 * 根据配置项 drama.video.provider 选择 agnes 或 mock 实现，供直接注入使用。
 */
@Configuration
public class VideoProviderConfig {

    @Bean
    public VideoProvider videoProvider(@Value("${drama.video.provider:mock}") String name,
                                       @Qualifier("agnesVideoProvider") VideoProvider agnes,
                                       @Qualifier("mockVideoProvider") VideoProvider mock) {
        if ("agnes".equals(name)) {
            return agnes;
        }
        return mock;
    }
}
