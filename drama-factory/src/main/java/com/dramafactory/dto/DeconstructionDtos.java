package com.dramafactory.dto;

import java.time.LocalDateTime;
import java.util.List;

import jakarta.validation.constraints.NotNull;

/**
 * 视频拆解 API 的请求/响应 DTO 集合。
 */
public final class DeconstructionDtos {

    private DeconstructionDtos() {
    }

    /**
     * 单个镜头 DTO。
     *
     * @param id             主键
     * @param shotNo         镜头序号
     * @param startSec       起始秒数
     * @param endSec         结束秒数
     * @param durationSec    时长秒数
     * @param keyframeUrl    关键帧 URL
     * @param segmentRole    片段角色
     * @param durationClass  时长分类
     * @param description    画面描述
     * @param shotSizeLabel  景别标签
     * @param cameraMoveLabel 运镜标签
     * @param promptGeneric  通用提示词
     * @param promptSeedance Seedance 提示词
     */
    public static record ShotDto(
            Long id,
            Integer shotNo,
            Double startSec,
            Double endSec,
            Double durationSec,
            String keyframeUrl,
            String segmentRole,
            String durationClass,
            String description,
            String shotSizeLabel,
            String cameraMoveLabel,
            String promptGeneric,
            String promptSeedance
    ) {
    }

    /**
     * 拆解摘要 DTO。
     *
     * @param id                  主键
     * @param projectId           项目 ID
     * @param assetId             资产 ID
     * @param sourceName          源文件名
     * @param status              状态
     * @param errorMessage        错误信息
     * @param durationSec         总时长秒数
     * @param width               画面宽度
     * @param height              画面高度
     * @param fps                 帧率
     * @param bitRate             码率
     * @param shotCount           镜头数
     * @param avgShotDurationSec  平均镜头时长秒数
     * @param cutsPerMinute       每分钟切镜数
     * @param rhythmClass         节奏分类
     * @param hookEndSec          钩子结束秒数
     * @param createdAt           创建时间
     * @param updatedAt           更新时间
     */
    public static record SummaryDto(
            Long id,
            Long projectId,
            Long assetId,
            String sourceName,
            String status,
            String errorMessage,
            Double durationSec,
            Integer width,
            Integer height,
            Double fps,
            Long bitRate,
            Integer shotCount,
            Double avgShotDurationSec,
            Double cutsPerMinute,
            String rhythmClass,
            Double hookEndSec,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }

    /**
     * 拆解详情 DTO，含完整结果 JSON 与镜头列表。
     *
     * @param id                  主键
     * @param projectId           项目 ID
     * @param assetId             资产 ID
     * @param sourceName          源文件名
     * @param status              状态
     * @param errorMessage        错误信息
     * @param durationSec         总时长秒数
     * @param width               画面宽度
     * @param height              画面高度
     * @param fps                 帧率
     * @param bitRate             码率
     * @param shotCount           镜头数
     * @param avgShotDurationSec  平均镜头时长秒数
     * @param cutsPerMinute       每分钟切镜数
     * @param rhythmClass         节奏分类
     * @param hookEndSec          钩子结束秒数
     * @param createdAt           创建时间
     * @param updatedAt           更新时间
     * @param resultJson          完整结果 JSON
     * @param shots               镜头列表
     */
    public static record DetailDto(
            Long id,
            Long projectId,
            Long assetId,
            String sourceName,
            String status,
            String errorMessage,
            Double durationSec,
            Integer width,
            Integer height,
            Double fps,
            Long bitRate,
            Integer shotCount,
            Double avgShotDurationSec,
            Double cutsPerMinute,
            String rhythmClass,
            Double hookEndSec,
            LocalDateTime createdAt,
            LocalDateTime updatedAt,
            String resultJson,
            List<ShotDto> shots
    ) {
    }

    /**
     * 基于资产创建拆解请求。
     *
     * @param assetId 资产 ID
     */
    public static record CreateFromAssetRequest(
            @NotNull Long assetId
    ) {
    }

    /**
     * 生成镜头请求。
     *
     * @param episodeId 分集 ID
     */
    public static record GenerateShotsRequest(
            @NotNull Long episodeId
    ) {
    }

    /**
     * 生成镜头响应。
     *
     * @param deconstructionId 拆解 ID
     * @param episodeId        分集 ID
     * @param createdCount     创建数量
     * @param shotIds          镜头 ID 列表
     */
    public static record GenerateShotsResponse(
            Long deconstructionId,
            Long episodeId,
            Integer createdCount,
            List<Long> shotIds
    ) {
    }
}
