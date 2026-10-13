package com.dramafactory.service.video;

/**
 * 熔断器打开时抛出的异常。
 *
 * <p>当 Resilience4j 的 CircuitBreaker 处于 OPEN 状态时，任何对被保护资源的调用都会被
 * 直接拒绝并抛出 {@link io.github.resilience4j.circuitbreaker.CallNotPermittedException}，
 * 本装饰器会将其转换为本异常向上抛出。</p>
 *
 * <p>该异常由 {@code VideoTaskService} 的 failOrRetry 统一捕获，走指数退避重试逻辑，
 * 避免在熔断窗口期内对下游（如 Agnes 视频服务）持续打点。</p>
 */
public class ProviderCircuitOpenException extends RuntimeException {

    /**
     * 构造器：仅携带描述信息。
     *
     * @param message 异常描述
     */
    public ProviderCircuitOpenException(String message) {
        super(message);
    }

    /**
     * 构造器：携带描述信息与根因。
     *
     * @param message 异常描述
     * @param cause   根因异常（通常是 CallNotPermittedException）
     */
    public ProviderCircuitOpenException(String message, Throwable cause) {
        super(message, cause);
    }
}

