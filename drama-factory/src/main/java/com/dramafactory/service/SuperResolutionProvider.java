package com.dramafactory.service;

import java.nio.file.Path;

/**
 * 真超分（super-resolution）能力接口（可选增强）。
 * 无可用超分能力时由 NoOpSuperResolutionProvider 占位，调用方自动降级为普通升采样。
 */
public interface SuperResolutionProvider {

    /** 是否有可用超分能力。 */
    boolean isAvailable();

    /**
     * 对低分辨率输入做超分增强。
     *
     * @param input   输入视频
     * @param workDir 工作目录（输出与中间文件落盘处）
     * @return 增强后的视频路径
     */
    Path enhance(Path input, Path workDir);
}
