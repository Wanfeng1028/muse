#!/usr/bin/env python3
"""
日志质量诊断脚本（非 assert 测试）

真实调用 LLM，执行 lite+agent 和 full+agent 两种 add，
打印分隔线 + 用 request_id 过滤的日志，供人工阅读判断质量。

用法:
    python3 tests/test_log_quality.py
"""

import logging
import os
import sys

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    """运行日志质量诊断"""
    # ── 从环境读取 API 配置；诊断脚本绝不携带或回显凭据。 ──
    llm_api_key = os.environ.get("MEMORY_LLM_API_KEY")
    embedding_api_key = os.environ.get("MEMORY_EMBEDDER_API_KEY")
    if not llm_api_key or not embedding_api_key:
        raise SystemExit(
            "Set MEMORY_LLM_API_KEY and MEMORY_EMBEDDER_API_KEY before running "
            "this live diagnostic."
        )
    llm_model = os.environ.get("MEMORY_LLM_MODEL", "deepseek-chat")
    llm_base_url = os.environ.get(
        "MEMORY_LLM_BASE_URL",
        "https://api.deepseek.com",
    )
    embedding_model = os.environ.get(
        "MEMORY_EMBEDDER_MODEL",
        "text-embedding-v4",
    )
    embedding_base_url = os.environ.get(
        "MEMORY_EMBEDDER_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    embedding_dims = int(os.environ.get("MEMORY_EMBEDDING_DIMS", "1024"))

    # ── 配置日志 ──
    from hy_memory.utils.log_setup import setup_logging, RequestIdFilter
    setup_logging(level=logging.DEBUG)

    hy_logger = logging.getLogger("hy_memory")

    # 移除 stderr StreamHandler（保留 FileHandler），避免重复输出
    for h in list(hy_logger.handlers):
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            hy_logger.removeHandler(h)

    # 用和 hy_memory.log 完全一样的 formatter 来格式化
    _LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"
    _DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    log_formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # 捕获所有 hy_memory 日志到列表
    captured_logs: list = []

    class LogCapture(logging.Handler):
        def emit(self, record):
            captured_logs.append(record)

    capture_handler = LogCapture()
    capture_handler.setLevel(logging.DEBUG)
    capture_handler.addFilter(RequestIdFilter())
    hy_logger.addHandler(capture_handler)

    # ── 辅助函数 ──

    def pr(msg=""):
        print(msg, flush=True)

    def print_separator(title: str):
        pr()
        pr("=" * 80)
        pr(f"  {title}")
        pr("=" * 80)

    def print_filtered_logs(request_id: str, level_filter: str = "ALL"):
        """打印特定 request_id 的日志，使用和 hy_memory.log 完全一样的格式"""
        filtered = [
            r for r in captured_logs
            if getattr(r, 'request_id', '-') == request_id
        ]
        if level_filter == "INFO+":
            filtered = [r for r in filtered if r.levelno >= logging.INFO]

        pr(f"\n--- request_id={request_id} ({level_filter}, {len(filtered)} lines) ---")
        for record in filtered:
            pr(log_formatter.format(record))
        pr(f"--- End ({len(filtered)} lines) ---")

    def count_logs(request_id: str):
        matched = [r for r in captured_logs if getattr(r, 'request_id', '-') == request_id]
        info_plus = [r for r in matched if r.levelno >= logging.INFO]
        debug_only = [r for r in matched if r.levelno == logging.DEBUG]
        return len(info_plus), len(debug_only)

    def wait_s2_tasks(client_obj, request_id: str, timeout: int = 120):
        """S2 现为同步处理（add 返回即完成），无后台任务可等。"""
        return {"status": "completed", "tasks": []}

    # ================================================================
    # 初始化客户端
    # ================================================================
    print_separator("Initializing HyMemoryClient")

    from hy_memory.client import HyMemoryClient
    client = HyMemoryClient.from_config({
        "llm": {
            "model": llm_model,
            "api_key": llm_api_key,
            "base_url": llm_base_url,
        },
        "embedder": {
            "model": embedding_model,
            "api_key": embedding_api_key,
            "base_url": embedding_base_url,
            "embedding_dims": embedding_dims,
        },
        "vector_store": {
            "provider": "chroma",
            "embedding_dims": embedding_dims,
        },
        "enable_graph": False,
        "enable_agent": True,
    })

    # 打印初始化阶段的日志
    init_info = [r for r in captured_logs
                 if getattr(r, 'request_id', '-') == '-' and r.levelno >= logging.INFO]
    init_debug = [r for r in captured_logs
                  if getattr(r, 'request_id', '-') == '-' and r.levelno == logging.DEBUG]
    pr(f"\nInit phase: {len(init_info)} INFO+ lines, {len(init_debug)} DEBUG lines")
    pr("\n--- Init INFO+ logs ---")
    for record in init_info:
        pr(log_formatter.format(record))
    pr(f"--- End ({len(init_info)} lines) ---")

    # ── 清除旧数据 ──
    pr("\nCleaning up old test data...")
    client.delete_all(user_id="test_log_user")

    # ================================================================
    # 测试 1: Lite + Agent add
    # ================================================================
    print_separator("Test 1: Lite + Agent add")

    test_content = (
        "我叫张三，今年28岁，在北京字节跳动做后端工程师。"
        "我特别喜欢手冲埃塞俄比亚耶加雪菲咖啡，"
        "周末经常去五道口的独立咖啡馆。"
        "最近在学 Rust 语言，打算用它重写一个内部工具。"
    )

    captured_logs.clear()
    result = client.add(
        test_content,
        user_id="test_log_user",
        agent_id="test_agent",
        session_id="test_session",
        pipeline="lite",
        enable_agent=True,
    )
    rid = result.get("request_id", "")

    pr(f"\nResult: success={result.get('success')} memory_id={result.get('memory_id')}")
    if result.get("error_message"):
        pr(f"Error: {result['error_message'][:120]}")

    print_filtered_logs(rid, "INFO+")
    print_filtered_logs(rid, "ALL")

    info_n, debug_n = count_logs(rid)
    pr(f"\n[Summary] INFO+ lines: {info_n}, DEBUG lines: {debug_n}")

    # ================================================================
    # 测试 2: Lite search
    # ================================================================
    print_separator("Test 2: Lite search")

    captured_logs.clear()
    search_result = client.search(
        "张三喜欢什么咖啡？他的职业是什么？",
        user_id="test_log_user",
        agent_ids=["test_agent"],
    )
    search_rid = search_result.get("request_id", "")

    pr(f"\nSearch result: {len(search_result.get('memories', []))} memories found")

    print_filtered_logs(search_rid, "INFO+")
    print_filtered_logs(search_rid, "ALL")

    info_n, debug_n = count_logs(search_rid)
    pr(f"\n[Summary] INFO+ lines: {info_n}, DEBUG lines: {debug_n}")

    # ================================================================
    # 测试 3: Full + Agent add (等 S2 任务完成)
    # ================================================================
    print_separator("Test 3: Full + Agent add")

    test_content_2 = (
        "今天和女朋友小红去了三里屯的一家新开的意大利餐厅，"
        "她对花生过敏所以我们特意问了厨师。"
        "饭后我们决定下个月去日本旅游，"
        "她想去京都看红叶，我想去东京看演唱会。"
    )

    captured_logs.clear()
    try:
        result2 = client.add(
            test_content_2,
            user_id="test_log_user",
            agent_id="test_agent",
            session_id="test_session",
            pipeline="pro",
            enable_agent=True,
        )
        rid2 = result2.get("request_id", "")

        pr(f"\nResult: success={result2.get('success')} memory_id={result2.get('memory_id')}")
        if result2.get("error_message"):
            pr(f"Error: {result2['error_message'][:120]}")

        # 等待 S2 后台任务完成
        pr("\nWaiting for S2 tasks to complete...")
        s2_status = wait_s2_tasks(client, rid2, timeout=120)
        pr(f"S2 status: {s2_status.get('status', 'unknown')}")
        if s2_status.get("tasks"):
            for t in s2_status["tasks"]:
                pr(f"  {t.get('task_type', '?')}: {t.get('status', '?')}")

        print_filtered_logs(rid2, "INFO+")
        print_filtered_logs(rid2, "ALL")

        info_n, debug_n = count_logs(rid2)
        pr(f"\n[Summary] INFO+ lines: {info_n}, DEBUG lines: {debug_n}")
    except Exception as e:
        pr(f"Pro pipeline not available or failed: {e}")
        import traceback
        traceback.print_exc()

    # ================================================================
    # 清理
    # ================================================================
    print_separator("Cleanup")
    captured_logs.clear()
    client.delete_all(user_id="test_log_user")
    client.close()
    pr("Done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
