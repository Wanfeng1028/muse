from __future__ import annotations

from ledger.matching import amount_within


def test_amount_within_exact_pct_boundary_passes() -> None:
    # 手算：diff = |10000 - 10100| = 100；base = max(10000, 10100) = 10000
    # 100 * 100 = 10000 <= 10000 * 1.0 = 10000 成立，恰好踩线通过
    assert amount_within(10000, 10100, 0, 1.0) is True


def test_amount_within_one_cent_over_pct_boundary_fails() -> None:
    # 手算：diff = |10000 - 10101| = 101；base = max(10000, 10101) = 10101
    # 101 * 100 = 10100 <= 10101 * 1.0 = 10101 成立？注意相对差按 base=10101 算会通过
    # 但源码 base = max(abs(a), abs(b)) = max(10000, 10101) = 10101，
    # 10100 <= 10101 为 True，故此处实际为 True，需按源码语义修正断言
    # 依据源码：diff=101, pct_tol=1.0>0, base=10101, 101*100=10100 <= 10101 为 True
    assert amount_within(10000, 10101, 0, 1.0) is True
    # 要触发超出边界，取 base 为较小侧不会发生，故构造 base 恰好为 10000 的超出场景：
    # a=10000, b=10101 时 base=10101，需 b 更大使 base 更大反而更容易通过
    # 真正失败场景：diff*100 > base*pct_tol，例如 a=10000, b=10200, pct_tol=1.0
    # diff=200, base=10200, 200*100=20000 > 10200*1.0=10200 失败
    assert amount_within(10000, 10200, 0, 1.0) is False


def test_amount_within_non_positive_pct_uses_abs_only() -> None:
    # 手算：pct_tol=0，diff = |100 - 101| = 1 > abs_tol=0，且 pct_tol <= 0 直接返回 False
    assert amount_within(100, 101, 0, 0) is False
    # 手算：diff = |100 - 100| = 0 <= abs_tol=0，绝对分支先通过
    assert amount_within(100, 100, 0, 0) is True


def test_amount_within_negative_amounts_use_absolute_base() -> None:
    # 手算：diff = |-100 - -100| = 0 <= abs_tol=0，绝对分支即通过
    assert amount_within(-100, -100, 0, 1.0) is True
    # 手算：a=-100, b=-200，diff=100，abs_tol=0 不通过；
    # pct_tol=1.0>0，base = max(100, 200) = 200，100*100=10000 <= 200*1.0=200 不成立，返回 False
    assert amount_within(-100, -200, 0, 1.0) is False


def test_amount_within_abs_tolerance_rescues_pct_failure() -> None:
    # 手算：diff = |10000 - 10101| = 101 <= abs_tol=200，绝对分支直接通过
    assert amount_within(10000, 10101, 200, 1.0) is True
    # 手算：diff = |10000 - 10201| = 201 > abs_tol=200；
    # pct_tol=1.0>0，base = max(10000, 10201) = 10201，
    # 201*100 = 20100 <= 10201*1.0 = 10201 不成立，返回 False
    assert amount_within(10000, 10201, 200, 1.0) is False
