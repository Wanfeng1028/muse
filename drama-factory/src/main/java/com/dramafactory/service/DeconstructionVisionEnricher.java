package com.dramafactory.service;

import java.nio.file.Path;
import java.util.Optional;

/**
 * 关键帧视觉理解增强接口——把关键帧送视觉模型补画面描述/景别/运镜；
 * 当前默认实现为 NoOp（不做任何识别），报告中相关字段标注待 AI 增强。
 */
public interface DeconstructionVisionEnricher {

    /**
     * 视觉增强结果记录。
     *
     * @param description      画面描述
     * @param shotSizeLabel    景别标签
     * @param cameraMoveLabel  运镜标签
     */
    record Enrichment(String description, String shotSizeLabel, String cameraMoveLabel) {
    }

    /**
     * 对单个关键帧执行视觉理解增强。
     *
     * @param keyframeFile 关键帧文件路径
     * @param shotNo       镜头序号
     * @param startSec     镜头起始秒数
     * @param endSec       镜头结束秒数
     * @return 增强结果，若无可用视觉模型则返回 {@link Optional#empty()}
     */
    Optional<Enrichment> enrich(Path keyframeFile, int shotNo, double startSec, double endSec);
}
