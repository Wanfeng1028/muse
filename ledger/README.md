ledger/
├── src/
│   └── ledger/
│       ├── __init__.py
│       ├── main.py            # FastAPI 应用入口、页面路由、静态文件挂载
│       ├── config.py          # 环境变量读取（LEDGER_DB / LEDGER_HOST / LEDGER_PORT）
│       ├── db.py              # create_async_engine / async_sessionmaker / Base
│       ├── models.py          # 六张表的 ORM 模型定义
│       ├── schemas.py         # Pydantic 请求/响应模型
│       ├── services.py        # 业务逻辑（余额计算、预算统计、规则校验）
│       ├── api/               # /api 路由：accounts / categories / transactions
│       │                      #            budgets / stats / import_export / recurring
│       ├── charts.py          # 内联 SVG 图表生成
│       ├── seed.py            # 预置常用分类
│       └── templates/         # Jinja2 模板（仪表盘、交易、账户、分类、预算…）
├── tests/                     # pytest 测试用例
├── data/                      # SQLite 数据库文件默认目录
├── pyproject.toml
├── Makefile
├── Dockerfile
└── README.md
