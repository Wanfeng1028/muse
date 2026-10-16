#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 Prometheus 告警规则文件。

用法：
    python3 scripts/check-alert-rules.py <rules.yml> [<rules2.yml> ...]

校验内容：
    硬错误（ERROR，会导致退出码非 0）：
        - 顶层缺少 groups 字段，或 groups 不是列表
        - 每个 group 缺少 name 字段
        - 每条 rule 缺少 alert 字段
        - 每条 rule 缺少 expr 字段
        - duration 字段（for / keep_firing_for）格式非法
        - labels / annotations 不是 map
        - severity 标签取值非法（必须是 critical / warning / info 之一）
        - annotations 缺少 summary 或 description
    软警告（WARN，不影响退出码）：
        - expr 中出现的疑似指标名无法在已知指标集合中找到

依赖：仅标准库 + PyYAML。
"""

import re
import sys

import yaml

# 允许的 severity 取值
VALID_SEVERITIES = {"critical", "warning", "info"}

# duration 合法格式：数字 + 单位（ms/s/m/h/d/w/y），可组合
DURATION_RE = re.compile(r"^(\d+(\.\d+)?(ms|s|m|h|d|w|y))+$")

# range duration 字面量，例如 [5m] [1h30m]
RANGE_DURATION_RE = re.compile(r"\[\d+(\.\d+)?(ms|s|m|h|d|w|y)\]")

# 花括号选择器块，例如 {status=~"5..",job="api"}
SELECTOR_BLOCK_RE = re.compile(r"\{[^{}]*\}")

# 双引号 / 单引号字符串字面量
STRING_LITERAL_RE = re.compile(r"\"[^\"]*\"|'[^']*'")

# 指标名 token：字母或下划线开头，后跟字母数字下划线冒号
METRIC_TOKEN_RE = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")

# 已知指标集合（用于 WARN 判定，可按需扩展）
KNOWN_METRICS = {
    "up",
    "http_requests_total",
    "http_request_duration_seconds",
    "http_request_duration_seconds_bucket",
    "http_request_duration_seconds_sum",
    "http_request_duration_seconds_count",
    "auth_ops_total",
    "ws_connections",
    "vfs_files_total",
    "vfs_bytes_total",
    "shares_total",
    "node_cpu_seconds_total",
    "node_memory_MemAvailable_bytes",
    "node_filesystem_avail_bytes",
    "process_cpu_seconds_total",
    "process_resident_memory_bytes",
}

# PromQL 关键字 / 函数名 / 聚合算子，不算指标名
PROMQL_KEYWORDS = {
    "and", "or", "unless", "by", "without", "on", "ignoring", "group_left",
    "group_right", "offset", "bool", "inf", "nan", "true", "false",
    "sum", "min", "max", "avg", "group", "stddev", "stdvar", "count",
    "count_values", "bottomk", "topk", "quantile", "rate", "irate",
    "increase", "delta", "idelta", "deriv", "predict_linear", "histogram_quantile",
    "abs", "ceil", "floor", "round", "clamp", "clamp_max", "clamp_min",
    "exp", "ln", "log2", "log10", "sqrt", "sgn", "sort", "sort_desc",
    "time", "timestamp", "vector", "scalar", "label_replace", "label_join",
    "avg_over_time", "min_over_time", "max_over_time", "sum_over_time",
    "count_over_time", "quantile_over_time", "stddev_over_time",
    "stdvar_over_time", "last_over_time", "present_over_time",
    "absent", "absent_over_time", "changes", "resets", "day_of_month",
    "day_of_week", "days_in_month", "hour", "minute", "month", "year",
}


def extract_metric_tokens(expr):
    """从 PromQL 表达式里提取疑似指标名。

    清洗顺序：
        1. 删掉整个 {...} 选择器块（含其中的 label 名、操作符、值）
        2. 删掉双引号 / 单引号字符串字面量
        3. 删掉 range duration 字面量，例如 [5m]
        4. 删掉 by (...)/without (...) 分组子句
        5. 再按 token 正则切分，过滤关键字与函数名
    """
    if not isinstance(expr, str):
        return set()

    text = SELECTOR_BLOCK_RE.sub(" ", expr)
    text = STRING_LITERAL_RE.sub(" ", text)
    text = RANGE_DURATION_RE.sub(" ", text)
    # 去掉 by (...)/without (...) 分组子句里的 label 名
    text = re.sub(r"\b(?:by|without)\s*\([^()]*\)", " ", text)

    tokens = set()
    for tok in METRIC_TOKEN_RE.findall(text):
        low = tok.lower()
        if low in PROMQL_KEYWORDS:
            continue
        tokens.add(tok)
    return tokens


def validate_duration(value, field, rule_name, errors):
    """校验 duration 字段格式。"""
    if isinstance(value, (int, float)):
        return
    if isinstance(value, str) and DURATION_RE.match(value):
        return
    errors.append(
        "rule %s: 字段 %s 的 duration 格式非法: %r" % (rule_name, field, value)
    )


def validate_rule(rule, group_name, index, errors, warnings):
    """校验单条告警规则。"""
    if not isinstance(rule, dict):
        errors.append("group %s: 第 %d 条 rule 不是 map" % (group_name, index + 1))
        return

    rule_name = rule.get("alert")
    if not rule_name:
        errors.append("group %s: 第 %d 条 rule 缺少 alert 字段" % (group_name, index + 1))
        rule_name = "<rule#%d>" % (index + 1)

    if "expr" not in rule or rule.get("expr") in (None, ""):
        errors.append("rule %s: 缺少 expr 字段" % rule_name)

    for field in ("for", "keep_firing_for"):
        if field in rule:
            validate_duration(rule[field], field, rule_name, errors)

    labels = rule.get("labels")
    if labels is not None and not isinstance(labels, dict):
        errors.append("rule %s: labels 不是 map" % rule_name)
    elif isinstance(labels, dict):
        sev = labels.get("severity")
        if sev is not None and sev not in VALID_SEVERITIES:
            errors.append(
                "rule %s: severity 取值非法: %r（应为 critical/warning/info 之一）"
                % (rule_name, sev)
            )

    annotations = rule.get("annotations")
    if annotations is not None and not isinstance(annotations, dict):
        errors.append("rule %s: annotations 不是 map" % rule_name)
    elif isinstance(annotations, dict):
        for key in ("summary", "description"):
            if key not in annotations:
                errors.append("rule %s: annotations 缺少 %s" % (rule_name, key))

    expr = rule.get("expr")
    if isinstance(expr, str):
        for tok in extract_metric_tokens(expr):
            if tok not in KNOWN_METRICS:
                warnings.append(
                    "rule %s: expr 中疑似未知指标 %r" % (rule_name, tok)
                )


def validate_group(group, index, errors, warnings):
    """校验单个 group。"""
    if not isinstance(group, dict):
        errors.append("第 %d 个 group 不是 map" % (index + 1))
        return 0

    group_name = group.get("name")
    if not group_name:
        errors.append("第 %d 个 group 缺少 name 字段" % (index + 1))
        group_name = "<group#%d>" % (index + 1)

    rules = group.get("rules")
    if not isinstance(rules, list):
        errors.append("group %s: rules 不是列表或缺失" % group_name)
        return 0

    for i, rule in enumerate(rules):
        validate_rule(rule, group_name, i, errors, warnings)
    return len(rules)


def check_file(path):
    """校验单个文件，返回 (error_count, warn_count, group_count, rule_count)。"""
    errors = []
    warnings = []

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError:
        print("ERROR: %s: 文件不存在" % path)
        return 1, 0, 0, 0
    except yaml.YAMLError as exc:
        print("ERROR: %s: YAML 解析失败: %s" % (path, exc))
        return 1, 0, 0, 0

    if not isinstance(data, dict):
        errors.append("顶层结构不是 map")
        data = {}

    groups = data.get("groups")
    if groups is None:
        errors.append("顶层缺少 groups 字段")
        groups = []
    elif not isinstance(groups, list):
        errors.append("groups 不是列表")
        groups = []

    rule_count = 0
    for i, group in enumerate(groups):
        rule_count += validate_group(group, i, errors, warnings)

    for msg in errors:
        print("ERROR: %s: %s" % (path, msg))
    for msg in warnings:
        print("WARN: %s: %s" % (path, msg))

    if not errors and not warnings:
        print("OK: %s (%d groups, %d rules)" % (path, len(groups), rule_count))
    elif not errors:
        print(
            "OK: %s (%d groups, %d rules, %d warnings)"
            % (path, len(groups), rule_count, len(warnings))
        )

    return len(errors), len(warnings), len(groups), rule_count


def main(argv):
    if len(argv) < 2:
        print("用法: python3 scripts/check-alert-rules.py <rules.yml> [...]")
        return 2

    total_errors = 0
    for path in argv[1:]:
        err_count, _warn_count, _g, _r = check_file(path)
        total_errors += err_count

    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))