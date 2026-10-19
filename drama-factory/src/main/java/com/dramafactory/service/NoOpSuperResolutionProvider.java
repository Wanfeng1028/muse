package com.dramafactory.service;

import org.springframework.stereotype.Service;

import java.nio.file.Path;

/**
 * 默认超分占位实现：当前无可用超分能力（无 GPU、无第三方超分 API），
 * isAvailable() 恒为 false，调用方降级为普通 ffmpeg 升采样并在日志明示。
 */
@Service
public class NoOpSuperResolutionProvider implements SuperResolutionProvider {

    @Override
    public boolean isAvailable() {
        return false;
    }

    @Override
    public Path enhance(Path input, Path workDir) {
        throw new UnsupportedOperationException("无可用超分能力");
    }
}
