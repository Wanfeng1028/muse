package com.dramafactory.service.byok;

import java.net.http.HttpRequest;

/**
 * BYOK Provider 的 HTTP 发送接缝。
 * 生产路径走真实 HttpClient；测试注入录制回放的假网关，全程无 socket、零真实网络。
 */
@FunctionalInterface
public interface ByokHttpGateway {

    /** 网关响应：HTTP 状态码 + 响应体文本。 */
    record GatewayResponse(int statusCode, String body) {
    }

    /**
     * 发送请求并返回状态码与响应体。
     *
     * @param request 已组装好的请求（含 URL、header、body）
     * @return 状态码与响应体
     * @throws Exception 网络层异常由调用方按原逻辑包装
     */
    GatewayResponse exchange(HttpRequest request) throws Exception;
}
