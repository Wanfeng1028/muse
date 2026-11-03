package com.dramafactory.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 定时任务配置。
 * 开启 @Scheduled 支持，用于视频任务状态机的定时轮询（processDueTasks）。
 */
@Configuration
@EnableScheduling
public class SchedulingConfig {
}
