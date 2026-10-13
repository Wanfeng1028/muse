package com.dramafactory.service;

/**
 * AI 剧本生成不可用异常。
 *
 * <p>当 AI 剧本生成能力不可用时抛出，可能的原因包括：</p>
 * <ul>
 *     <li>配置未启用（{@code drama.script.llm.enabled=false}）；</li>
 *     <li>调用大模型失败（网络异常 / 非 2xx 响应 / 多次重试后仍失败）；</li>
 *     <li>大模型返回的内容格式无效，无法解析为剧本场景。</li>
 * </ul>
 *
 * <p>调用方（如 {@link ScriptService}）捕获此异常后应降级为模板生成，
 * 以保证剧本生成链路始终可用。</p>
 */
public class LlmScriptUnavailableException extends RuntimeException {

    /**
     * 构造异常。
     *
     * @param message 异常描述
     */
    public LlmScriptUnavailableException(String message) {
        super(message);
    }

    /**
     * 构造异常。
     *
     * @param message 异常描述
     * @param cause   原始异常
     */
    public LlmScriptUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}

