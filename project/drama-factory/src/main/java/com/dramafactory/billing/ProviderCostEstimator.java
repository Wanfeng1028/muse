package com.dramafactory.billing;

import java.util.HashMap;
import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/**
 * 视频提供方单次生成费用估算组件。
 *
 * <p>用途：在视频路由提交生成任务之前，按提供方与时长估算所需费用，
 * 估算值仅用于预算预留与告警，不代表真实扣费。</p>
 *
 * <p>定价来源优先级：</p>
 * <ol>
 *     <li>配置覆盖：{@code drama.billing.cost-per-sec.<归一化提供方名>}，单位美元/秒；</li>
 *     <li>内置默认表（见 {@link #DEFAULT_COST_PER_SECOND}）。</li>
 * </ol>
 *
 * <p>默认表说明：以下均为 2026-10 按各提供方公开定价估算的参考值，实际费用以提供方账单为准。</p>
 */
@Component
public class ProviderCostEstimator {

    /**
     * 配置前缀：{@code drama.billing.cost-per-sec.<归一化提供方名>}。
     */
    private static final String COST_PER_SECOND_PREFIX = "drama.billing.cost-per-sec.";

    /**
     * 内置默认单价表，单位：美元/秒。
     *
     * <p>以下均为 2026-10 按各提供方公开定价估算的参考值，实际费用以提供方账单为准。</p>
     */
    private static final Map<String, Double> DEFAULT_COST_PER_SECOND = new HashMap<>();

    static {
        DEFAULT_COST_PER_SECOND.put("agnes", 0.08);
        DEFAULT_COST_PER_SECOND.put("minimax", 0.05);
        DEFAULT_COST_PER_SECOND.put("novai", 0.03);
        DEFAULT_COST_PER_SECOND.put("qwen", 0.02);
        // 邮件异步通道，按免费计
        DEFAULT_COST_PER_SECOND.put("doubao", 0.0);
        // 本地 CLI 渲染
        DEFAULT_COST_PER_SECOND.put("hyperframes", 0.0);
        // 本地渲染
        DEFAULT_COST_PER_SECOND.put("htmlrender", 0.0);
        // 本地生成
        DEFAULT_COST_PER_SECOND.put("painted", 0.0);
        DEFAULT_COST_PER_SECOND.put("mock", 0.0);
        // 本地
        DEFAULT_COST_PER_SECOND.put("comfyui", 0.0);
        // 本地
        DEFAULT_COST_PER_SECOND.put("local-h3", 0.0);
    }

    private final Environment environment;

    public ProviderCostEstimator(Environment environment) {
        this.environment = environment;
    }

    /**
     * 估算指定提供方的每秒费用（美元/秒）。
     *
     * @param providerName 提供方名称；为空或空白时返回 0.0
     * @return 每秒费用，单位美元/秒
     * @throws IllegalStateException 当配置覆盖值非法（解析失败、NaN、负数）时抛出
     */
    public double estimateUsdPerSecond(String providerName) {
        if (providerName == null || providerName.isBlank()) {
            return 0.0;
        }

        String normalized = normalize(providerName);
        String configKey = COST_PER_SECOND_PREFIX + normalized;
        String configured = environment.getProperty(configKey);
        if (configured != null) {
            double parsed;
            try {
                parsed = Double.parseDouble(configured.trim());
            } catch (NumberFormatException ex) {
                throw new IllegalStateException(
                        "配置项 " + configKey + " 的值无法解析为数字：" + configured, ex);
            }
            if (Double.isNaN(parsed)) {
                throw new IllegalStateException(
                        "配置项 " + configKey + " 的值非法（NaN）：" + configured);
            }
            if (parsed < 0.0) {
                throw new IllegalStateException(
                        "配置项 " + configKey + " 的值非法（负数）：" + configured);
            }
            return parsed;
        }

        Double defaultCost = DEFAULT_COST_PER_SECOND.get(normalized.toLowerCase());
        if (defaultCost != null) {
            return defaultCost;
        }
        return 0.0;
    }

    /**
     * 估算指定提供方在给定时长下的总费用。
     *
     * @param providerName 提供方名称
     * @param seconds      生成时长（秒）；小于等于 0 时返回 0.0
     * @return 估算总费用，单位美元
     * @throws IllegalStateException 当配置覆盖值非法时抛出
     */
    public double estimate(String providerName, int seconds) {
        if (seconds <= 0) {
            return 0.0;
        }
        return estimateUsdPerSecond(providerName) * seconds;
    }

    /**
     * 归一化提供方名称：将所有非字母数字字符替换为 {@code -}。
     *
     * <p>例如 {@code descriptor:agnes-turbo} 归一化为 {@code descriptor-agnes-turbo}。</p>
     *
     * @param providerName 原始提供方名称
     * @return 归一化后的名称
     */
    private String normalize(String providerName) {
        StringBuilder sb = new StringBuilder(providerName.length());
        for (int i = 0; i < providerName.length(); i++) {
            char c = providerName.charAt(i);
            if (Character.isLetterOrDigit(c)) {
                sb.append(c);
            } else {
                sb.append('-');
            }
        }
        return sb.toString();
    }
}
