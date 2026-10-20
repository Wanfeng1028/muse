package com.dramafactory.billing;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * ProviderCostEstimator 单元测试。
 * 覆盖默认费率、环境变量覆盖、非法配置 fail-fast、以及 estimate 的边界行为。
 */
class ProviderCostEstimatorTest {

    /** 构造一个无任何覆盖配置的估计器。 */
    private ProviderCostEstimator newDefaultEstimator() {
        return new ProviderCostEstimator(new MockEnvironment());
    }

    /** 构造一个带单个覆盖配置的估计器。 */
    private ProviderCostEstimator newEstimatorWithProperty(String key, String value) {
        MockEnvironment env = new MockEnvironment();
        env.setProperty(key, value);
        return new ProviderCostEstimator(env);
    }

    @Test
    void defaultRatesForKnownProviders() {
        ProviderCostEstimator estimator = newDefaultEstimator();
        assertEquals(0.08, estimator.estimateUsdPerSecond("agnes"), 1e-9, "agnes 默认费率应为 0.08");
        assertEquals(0.05, estimator.estimateUsdPerSecond("minimax"), 1e-9, "minimax 默认费率应为 0.05");
        assertEquals(0.03, estimator.estimateUsdPerSecond("novai"), 1e-9, "novai 默认费率应为 0.03");
        assertEquals(0.02, estimator.estimateUsdPerSecond("qwen"), 1e-9, "qwen 默认费率应为 0.02");
    }

    @Test
    void zeroRatesForFreeProviders() {
        ProviderCostEstimator estimator = newDefaultEstimator();
        assertEquals(0.0, estimator.estimateUsdPerSecond("doubao"), 1e-9, "doubao 费率应为 0");
        assertEquals(0.0, estimator.estimateUsdPerSecond("hyperframes"), 1e-9, "hyperframes 费率应为 0");
        assertEquals(0.0, estimator.estimateUsdPerSecond("htmlrender"), 1e-9, "htmlrender 费率应为 0");
        assertEquals(0.0, estimator.estimateUsdPerSecond("painted"), 1e-9, "painted 费率应为 0");
        assertEquals(0.0, estimator.estimateUsdPerSecond("mock"), 1e-9, "mock 费率应为 0");
        assertEquals(0.0, estimator.estimateUsdPerSecond("comfyui"), 1e-9, "comfyui 费率应为 0");
        assertEquals(0.0, estimator.estimateUsdPerSecond("local-h3"), 1e-9, "local-h3 费率应为 0");
    }

    @Test
    void unknownAndDescriptorAndNullNamesReturnZero() {
        ProviderCostEstimator estimator = newDefaultEstimator();
        assertEquals(0.0, estimator.estimateUsdPerSecond("unknown-provider"), 1e-9, "未知通道费率应为 0");
        assertEquals(0.0, estimator.estimateUsdPerSecond("descriptor:xxx"), 1e-9, "descriptor:xxx 费率应为 0");
        assertEquals(0.0, estimator.estimateUsdPerSecond(null), 1e-9, "null 名称费率应为 0");
    }

    @Test
    void blankNameReturnsZero() {
        ProviderCostEstimator estimator = newDefaultEstimator();
        assertEquals(0.0, estimator.estimateUsdPerSecond("   "), 1e-9, "空白名称费率应为 0");
        assertEquals(0.0, estimator.estimateUsdPerSecond(""), 1e-9, "空字符串名称费率应为 0");
    }

    @Test
    void nameLookupIsCaseInsensitive() {
        ProviderCostEstimator estimator = newDefaultEstimator();
        assertEquals(0.08, estimator.estimateUsdPerSecond("AGNES"), 1e-9, "大写 AGNES 应按 agnes 计");
    }

    @Test
    void overrideByPlainAlphabeticKey() {
        ProviderCostEstimator estimator = newEstimatorWithProperty("drama.billing.cost-per-sec.agnes", "0.5");
        assertEquals(0.5, estimator.estimateUsdPerSecond("agnes"), 1e-9, "环境变量应覆盖 agnes 费率");
    }

    @Test
    void overrideByDescriptorKey() {
        ProviderCostEstimator estimator =
                newEstimatorWithProperty("drama.billing.cost-per-sec.descriptor-agnes-turbo", "0.9");
        assertEquals(0.9, estimator.estimateUsdPerSecond("descriptor:agnes-turbo"), 1e-9,
                "环境变量应覆盖 descriptor:agnes-turbo 费率");
    }

    @Test
    void negativeOverrideValueFailsFast() {
        ProviderCostEstimator estimator = newEstimatorWithProperty("drama.billing.cost-per-sec.agnes", "-1");
        assertThrows(IllegalStateException.class, () -> estimator.estimateUsdPerSecond("agnes"),
                "非法负值配置应抛 IllegalStateException");
    }

    @Test
    void nonNumericOverrideValueFailsFast() {
        ProviderCostEstimator estimator = newEstimatorWithProperty("drama.billing.cost-per-sec.agnes", "abc");
        assertThrows(IllegalStateException.class, () -> estimator.estimateUsdPerSecond("agnes"),
                "非数字配置应抛 IllegalStateException");
    }

    @Test
    void estimateWithNonPositiveSecondsReturnsZero() {
        ProviderCostEstimator estimator = newDefaultEstimator();
        assertEquals(0.0, estimator.estimate("agnes", 0), 1e-9, "seconds 为 0 时应返回 0");
        assertEquals(0.0, estimator.estimate("agnes", -5), 1e-9, "seconds 为负时应返回 0");
    }

    @Test
    void estimateScalesWithSeconds() {
        ProviderCostEstimator estimator = newDefaultEstimator();
        assertEquals(0.8, estimator.estimate("agnes", 10), 1e-9, "agnes 10 秒应为 0.8");
    }

    @Test
    void estimateWithNullProviderReturnsZero() {
        ProviderCostEstimator estimator = newDefaultEstimator();
        assertEquals(0.0, estimator.estimate(null, 10), 1e-9, "null provider 应返回 0");
    }
}
