package com.dramafactory.billing;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * 计费总开关与预算策略配置组件。
 *
 * <p>四个配置项及其默认值：</p>
 * <ul>
 *     <li>{@code drama.billing.enabled}（默认 {@code true}）：计费总开关，关闭后视频路由会跳过一切账本操作。</li>
 *     <li>{@code drama.billing.mode}（默认 {@code WARN}）：预算模式，只允许 WARN / CAP（大小写不敏感）。
 *         WARN 仅记录告警继续预留，CAP 超预算直接抛异常。</li>
 *     <li>{@code drama.billing.budget-total-usd}（默认 {@code 100.0}）：总预算（美元），不允许为负数。</li>
 *     <li>{@code drama.billing.reserve-pct}（默认 {@code 0.1}）：预留占用比例，合法区间为 [0, 0.9]。</li>
 * </ul>
 *
 * <p>启动时通过 {@link PostConstruct} 做 fail-fast 校验，任一配置非法将抛出
 * {@link IllegalStateException} 中断启动。</p>
 */
@Component
public class BillingProperties {

    private final boolean enabled;
    private final String mode;
    private final double budgetTotalUsd;
    private final double reservePct;

    public BillingProperties(
            @Value("${drama.billing.enabled:true}") boolean enabled,
            @Value("${drama.billing.mode:WARN}") String mode,
            @Value("${drama.billing.budget-total-usd:100.0}") double budgetTotalUsd,
            @Value("${drama.billing.reserve-pct:0.1}") double reservePct) {
        this.enabled = enabled;
        this.mode = mode;
        this.budgetTotalUsd = budgetTotalUsd;
        this.reservePct = reservePct;
    }

    /**
     * 启动校验，非法配置直接中断启动。
     */
    @PostConstruct
    public void validate() {
        String normalizedMode = this.mode == null ? "" : this.mode.trim().toUpperCase();
        if (!"WARN".equals(normalizedMode) && !"CAP".equals(normalizedMode)) {
            throw new IllegalStateException(
                    "配置 drama.billing.mode 非法，当前值为 [" + this.mode + "]，合法取值为 WARN / CAP（大小写不敏感）");
        }
        if (this.budgetTotalUsd < 0) {
            throw new IllegalStateException(
                    "配置 drama.billing.budget-total-usd 非法，当前值为 [" + this.budgetTotalUsd + "]，合法范围为大于等于 0");
        }
        if (this.reservePct < 0 || this.reservePct > 0.9) {
            throw new IllegalStateException(
                    "配置 drama.billing.reserve-pct 非法，当前值为 [" + this.reservePct + "]，合法区间为 [0, 0.9]");
        }
    }

    public boolean isEnabled() {
        return enabled;
    }

    public String getMode() {
        return mode;
    }

    public double getBudgetTotalUsd() {
        return budgetTotalUsd;
    }

    public double getReservePct() {
        return reservePct;
    }

    /**
     * 将当前配置转换为预算策略对象。
     *
     * @return 预算策略
     */
    public BudgetPolicy toBudgetPolicy() {
        return new BudgetPolicy(
                BudgetMode.valueOf(getMode().trim().toUpperCase()),
                getBudgetTotalUsd(),
                getReservePct());
    }
}
