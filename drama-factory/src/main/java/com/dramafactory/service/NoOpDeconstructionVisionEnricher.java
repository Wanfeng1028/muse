package com.dramafactory.service;

import java.nio.file.Path;
import java.util.Optional;

import org.springframework.stereotype.Component;

/**
 * 关键帧视觉理解增强的空实现——恒返回 {@link Optional#empty()}。
 * <p>
 * 接入 BYOK 视觉模型时新增实现并以配置切换，本类不做任何猜测性填充。
 */
@Component
public class NoOpDeconstructionVisionEnricher implements DeconstructionVisionEnricher {

    /**
     * 恒返回空结果，不执行任何视觉识别。
     *
     * @param keyframeFile 关键帧文件路径
     * @param shotNo       镜头序号
     * @param startSec     镜头起始秒数
     * @param endSec       镜头结束秒数
     * @return {@link Optional#empty()}
     */
    @Override
    public Optional<Enrichment> enrich(Path keyframeFile, int shotNo, double startSec, double endSec) {
        return Optional.empty();
    }
}
