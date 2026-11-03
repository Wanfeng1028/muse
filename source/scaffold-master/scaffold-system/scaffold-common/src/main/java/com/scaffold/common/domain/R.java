package com.scaffold.common.domain;

import org.slf4j.MDC;

/**
 * Unified API response model.
 *
 * @param code 响应状态码
 * @param message 响应提示信息
 * @param data 响应业务数据
 * @param traceId 请求追踪 ID，用于日志排查
 */
public record R<T>(Integer code, String message, T data, String traceId) {

    public static final int SUCCESS_CODE = 200;
    public static final String SUCCESS_MESSAGE = "操作成功";

    public static <T> R<T> success(T data) {
        return new R<>(SUCCESS_CODE, SUCCESS_MESSAGE, data, MDC.get("traceId"));
    }

    public static <T> R<T> error(int code, String message) {
        return new R<>(code, message, null, MDC.get("traceId"));
    }
}
