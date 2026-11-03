package com.dramafactory.service.video;

/**
 * 视频提供方返回 429 限流时抛出的异常。
 * 调度器捕获该异常后，可根据 {@link #getRetryAfterSeconds()} 进行退避重试。
 */
public class RateLimitedException extends RuntimeException {

    /** 建议等待的秒数（退避重试间隔） */
    private final long retryAfterSeconds;

    /**
     * 构造限流异常。
     *
     * @param message           异常描述信息
     * @param retryAfterSeconds 建议等待的秒数
     */
    public RateLimitedException(String message, long retryAfterSeconds) {
        super(message);
        this.retryAfterSeconds = retryAfterSeconds;
    }

    /**
     * 获取建议等待的秒数。
     *
     * @return 建议等待秒数
     */
    public long getRetryAfterSeconds() {
        return retryAfterSeconds;
    }
}
