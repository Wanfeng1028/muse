package com.dramafactory.billing;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * BillingProperties 的配置绑定与校验测试。
 */
class BillingPropertiesTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withUserConfiguration(BillingProperties.class);

    /**
     * 不设置任何属性时应使用默认值。
     */
    @Test
    void shouldUseDefaultValuesWhenNoPropertyProvided() {
        runner.run(context -> {
            BillingProperties props = context.getBean(BillingProperties.class);
            assertTrue(props.isEnabled());
            assertEquals("WARN", props.getMode());
            assertEquals(100.0, props.getBudgetTotalUsd(), 1e-9);
            assertEquals(0.1, props.getReservePct(), 1e-9);

            BudgetPolicy policy = props.toBudgetPolicy();
            assertNotNull(policy);
            assertEquals(BudgetMode.WARN, policy.mode());
        });
    }

    /**
     * 自定义合法值应全部生效，且 mode 大小写不敏感。
     */
    @Test
    void shouldBindCustomValidValues() {
        runner.withPropertyValues(
                        "drama.billing.enabled=false",
                        "drama.billing.mode=cap",
                        "drama.billing.budget-total-usd=50",
                        "drama.billing.reserve-pct=0.2")
                .run(context -> {
                    BillingProperties props = context.getBean(BillingProperties.class);
                    assertFalse(props.isEnabled());
                    assertEquals("cap", props.getMode());
                    assertEquals(50.0, props.getBudgetTotalUsd(), 1e-9);
                    assertEquals(0.2, props.getReservePct(), 1e-9);

                    BudgetPolicy policy = props.toBudgetPolicy();
                    assertNotNull(policy);
                    assertEquals(BudgetMode.CAP, policy.mode());
                });
    }

    /**
     * 非法 mode 应导致上下文启动失败，且异常链中含 IllegalStateException。
     */
    @Test
    void shouldFailStartupWhenModeInvalid() {
        runner.withPropertyValues("drama.billing.mode=XXX")
                .run(context -> {
                    assertNotNull(context.getStartupFailure());
                });
    }

    /**
     * mode 为未知值时异常链应包含 IllegalStateException。
     */
    @Test
    void shouldContainIllegalStateExceptionWhenModeInvalid() {
        runner.withPropertyValues("drama.billing.mode=NOT_A_MODE")
                .run(context -> {
                    Throwable failure = context.getStartupFailure();
                    assertNotNull(failure);
                    assertTrue(hasCauseOfType(failure, IllegalStateException.class));
                });
    }

    /**
     * 负数预算应导致上下文启动失败。
     */
    @Test
    void shouldFailStartupWhenBudgetNegative() {
        runner.withPropertyValues("drama.billing.budget-total-usd=-1")
                .run(context -> {
                    Throwable failure = context.getStartupFailure();
                    assertNotNull(failure);
                    assertTrue(hasCauseOfType(failure, IllegalStateException.class));
                });
    }

    /**
     * reserve-pct 超过 0.9 应导致上下文启动失败。
     */
    @Test
    void shouldFailStartupWhenReservePctTooLarge() {
        runner.withPropertyValues("drama.billing.reserve-pct=1.5")
                .run(context -> {
                    Throwable failure = context.getStartupFailure();
                    assertNotNull(failure);
                    assertTrue(hasCauseOfType(failure, IllegalStateException.class));
                });
    }

    /**
     * reserve-pct 为负数应导致上下文启动失败。
     */
    @Test
    void shouldFailStartupWhenReservePctNegative() {
        runner.withPropertyValues("drama.billing.reserve-pct=-0.1")
                .run(context -> {
                    Throwable failure = context.getStartupFailure();
                    assertNotNull(failure);
                    assertTrue(hasCauseOfType(failure, IllegalStateException.class));
                });
    }

    /**
     * reserve-pct 取边界值 0 应合法。
     */
    @Test
    void shouldAcceptReservePctZero() {
        runner.withPropertyValues("drama.billing.reserve-pct=0")
                .run(context -> {
                    assertFalse(context.getStartupFailure() != null);
                    BillingProperties props = context.getBean(BillingProperties.class);
                    assertEquals(0.0, props.getReservePct(), 1e-9);
                });
    }

    /**
     * reserve-pct 取边界值 0.9 应合法。
     */
    @Test
    void shouldAcceptReservePctUpperBound() {
        runner.withPropertyValues("drama.billing.reserve-pct=0.9")
                .run(context -> {
                    assertFalse(context.getStartupFailure() != null);
                    BillingProperties props = context.getBean(BillingProperties.class);
                    assertEquals(0.9, props.getReservePct(), 1e-9);
                });
    }

    /**
     * mode 为 WARN 大写时合法，转换后 toBudgetPolicy 为 WARN。
     */
    @Test
    void shouldAcceptUppercaseWarnMode() {
        runner.withPropertyValues("drama.billing.mode=WARN")
                .run(context -> {
                    BillingProperties props = context.getBean(BillingProperties.class);
                    assertEquals(BudgetMode.WARN, props.toBudgetPolicy().mode());
                });
    }

    /**
     * 递归查找异常链中是否存在指定类型的异常。
     */
    private static boolean hasCauseOfType(Throwable throwable, Class<? extends Throwable> type) {
        Throwable current = throwable;
        while (current != null) {
            if (type.isInstance(current)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }
}
