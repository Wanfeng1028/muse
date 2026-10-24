"""确定性仿真账单生成器：为真实负载验证生成中文消费者账单 CSV。

供 scripts/load_test.py 与 tests/test_load_statement.py 复用。
同一 (year, month, seed) 输入输出完全相同。"""

import csv
import io
import random

MERCHANTS = [
    {"name": "美团外卖", "category": "餐饮", "direction": "out", "low": 15, "high": 60, "monthly": 22},
    {"name": "饿了么", "category": "餐饮", "direction": "out", "low": 12, "high": 55, "monthly": 14},
    {"name": "盒马鲜生", "category": "购物", "direction": "out", "low": 50, "high": 300, "monthly": 8},
    {"name": "京东", "category": "购物", "direction": "out", "low": 20, "high": 800, "monthly": 5},
    {"name": "淘宝", "category": "购物", "direction": "out", "low": 20, "high": 600, "monthly": 4},
    {"name": "拼多多", "category": "购物", "direction": "out", "low": 10, "high": 200, "monthly": 3},
    {"name": "滴滴出行", "category": "交通", "direction": "out", "low": 12, "high": 80, "monthly": 12},
    {"name": "地铁", "category": "交通", "direction": "out", "low": 4, "high": 12, "monthly": 20},
    {"name": "中国移动", "category": "日用", "direction": "out", "low": 38, "high": 88, "monthly": 1},
    {
        "name": "国家电网",
        "category": "日用",
        "direction": "out",
        "low": 30,
        "high": 200,
        "monthly": 2,
        "even_month_only": True,
    },
    {
        "name": "燃气公司",
        "category": "日用",
        "direction": "out",
        "low": 20,
        "high": 120,
        "monthly": 1,
        "odd_month_only": True,
    },
    {"name": "工资", "category": "工资", "direction": "in", "low": 8000, "high": 15000, "monthly": 1, "fixed_day": 10},
    {"name": "房租", "category": "购物", "direction": "out", "low": 2500, "high": 4000, "monthly": 1, "fixed_day": 1},
    {"name": "星巴克", "category": "餐饮", "direction": "out", "low": 25, "high": 60, "monthly": 4},
    {"name": "瑞幸咖啡", "category": "餐饮", "direction": "out", "low": 15, "high": 40, "monthly": 6},
    {"name": "海底捞", "category": "餐饮", "direction": "out", "low": 150, "high": 400, "monthly": 1},
    {"name": "药店", "category": "医疗", "direction": "out", "low": 20, "high": 200, "monthly": 2},
    {"name": "医院", "category": "医疗", "direction": "out", "low": 100, "high": 800, "monthly": 0.4},
    {"name": "电影院", "category": "娱乐", "direction": "out", "low": 40, "high": 120, "monthly": 2},
    {
        "name": "信用卡还款",
        "category": "购物",
        "direction": "out",
        "low": 1000,
        "high": 8000,
        "monthly": 1,
        "own_account": True,
    },
    {"name": "余额宝转入", "category": "购物", "direction": "out", "low": 500, "high": 3000, "monthly": 2},
]
CSV_HEADERS = ["交易日期", "交易对方", "交易摘要", "金额", "收/支"]
COLUMN_MAPPING = {
    "date": "交易日期",
    "counterparty": "交易对方",
    "summary": "交易摘要",
    "amount": "金额",
    "direction": "收/支",
}
SUFFIX = {
    "美团外卖": ["黄焖鸡米饭", "沙县小吃", "兰州拉面"],
    "饿了么": ["麻辣烫", "汉堡王"],
    "滴滴出行": ["上下班", "去机场"],
}


def _fmt_amount(rng, direction, low, high):
    v = round(rng.uniform(low, high), 2)
    if direction == "in":
        return f"{v:,.2f}" if v >= 1000 else f"{v:.2f}"
    r = rng.random()
    if r < 0.80:
        return f"-{v:.2f}"
    if r < 0.95:
        return f"({v:.2f})"
    return f"-{v:,.2f}" if v >= 1000 else f"-{v:.2f}"


def _fmt_date(rng, year, month, day):
    if rng.random() < 0.5:
        return f"{year}-{month:02d}-{day:02d}"
    return f"{year}年{month}月{day}日"


def generate_month_csv(year, month, seed=20261024):
    rng = random.Random(seed * 10000 + year * 100 + month)
    rows, expected = [], []
    for m in MERCHANTS:
        if m.get("even_month_only") and month % 2 == 1:
            continue
        if m.get("odd_month_only") and month % 2 == 0:
            continue
        n = max(1, round(m["monthly"])) if m["monthly"] >= 1 else (1 if rng.random() < m["monthly"] else 0)
        if m["monthly"] > 1:
            n = round(m["monthly"] * rng.uniform(0.8, 1.2))
        for _ in range(n):
            day = m.get("fixed_day") or rng.randint(1, 28)
            cp = "__OWN_ACCOUNT__" if m.get("own_account") else m["name"]
            sfx = rng.choice(SUFFIX.get(m["name"], ["消费"]))
            rows.append(
                [
                    _fmt_date(rng, year, month, day),
                    cp,
                    f"{m['name']}-{sfx}",
                    _fmt_amount(rng, m["direction"], m["low"], m["high"]),
                    "收入" if m["direction"] == "in" else "支出",
                ]
            )
            expected.append({"counterparty": cp, "category": m["category"], "direction": m["direction"]})
    rng.shuffle(rows)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEADERS)
    w.writerows(rows)
    return "\ufeff" + buf.getvalue(), expected
