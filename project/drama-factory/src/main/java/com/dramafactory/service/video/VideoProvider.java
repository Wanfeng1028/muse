package com.dramafactory.service.video;

import com.dramafactory.model.Shot;

/**
 * 视频提供方抽象接口。
 * 用于屏蔽不同视频生成服务（如 agnes、mock）的差异，
 * 上层通过统一契约提交任务并轮询状态。
 */
public interface VideoProvider {

    /**
     * 提供方侧任务状态。
     */
    enum RemoteStatus {
        /** 排队中 */
        QUEUED,
        /** 生成中 */
        PROCESSING,
        /** 已完成 */
        COMPLETED,
        /** 已失败 */
        FAILED
    }

    /**
     * 轮询结果。
     *
     * @param status       提供方侧任务状态
     * @param videoUrl     生成完成后的视频地址，未完成或失败时为 null
     * @param errorMessage 失败原因，成功或未完成时为 null
     * @param progress     进度百分比（0-100）
     */
    record ProbeResult(RemoteStatus status, String videoUrl, String errorMessage, int progress) {
    }

    /**
     * 提交视频生成任务。
     * prompt 优先取 {@link Shot#getVideoPrompt()}，为空时使用 {@link Shot#getDescription()}
     * 拼接景别与运镜的中文名。
     *
     * @param shot    分镜实体
     * @param seconds 目标视频时长（秒）
     * @return 提供方任务 ID
     */
    String submit(Shot shot, int seconds);

    /**
     * 轮询任务状态。
     *
     * @param providerTaskId 提供方任务 ID
     * @return 轮询结果
     */
    ProbeResult poll(String providerTaskId);

    /**
     * 连接自检结果状态。
     */
    enum ConnectivityStatus {
        /** 密钥有效、链路畅通 */
        OK,
        /** 密钥无效或鉴权失败 */
        AUTH_FAILED,
        /** 触发提供方限流 */
        RATE_LIMITED,
        /** 网络不可达（DNS / 超时 / 连接被拒） */
        UNREACHABLE,
        /** 服务方异常（非 2xx/4xx 预期外的响应） */
        PROVIDER_ERROR,
        /** 暂不支持连接自检 */
        UNSUPPORTED
    }

    /**
     * 连接自检结果。detail 为面向用户的说明文案，绝不包含任何密钥原文或片段。
     *
     * @param status 自检状态
     * @param detail 面向用户的说明（不得含密钥，status=OK 之外不得出现"成功"字样）
     */
    record ConnectivityResult(ConnectivityStatus status, String detail) {
    }

    /**
     * 连接自检：使用零费用负向探测（查询一个不存在的探测任务 ID）验证密钥与链路。
     * 实现必须严格按契约分类：只有真实 404 或 2xx 才可判 OK。
     *
     * <p>默认为不支持；各提供方按需重写。
     *
     * @return 自检结果
     */
    default ConnectivityResult probeConnectivity() {
        return new ConnectivityResult(ConnectivityStatus.UNSUPPORTED, "该提供方暂不支持连接自检");
    }

    /**
     * 返回提供方名称，例如 "agnes"、"mock"。
     *
     * @return 提供方名
     */
    String name();
}
