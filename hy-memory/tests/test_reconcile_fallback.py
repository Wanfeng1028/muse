"""reconcile 失败时必须兜底为「全部 ADD」，不能丢弃抽取结果。

一个暂存环境回归场景中，抽取已成功，但 reconcile 的 LLM 在重试后失败，
导致整批完好事实被丢弃，`memory_ops` 返回 0 条。
reconcile 只负责决定「新事实和旧记忆怎么合」，它不可用不代表抽取结果没价值。
宁可留重复（后续 dedup / reconcile 还能收拾）也不要丢内容。
"""

from hy_memory.agent.reconciler import MemoryReconciler, ReconcileResult


NEW = [
    "The user took a road trip in July 2023 to Banff, where he went skiing.",
    "The user is in a new romantic relationship as of August 2023.",
    "Sam offered to give the user tips on organizing a book club.",
]
META = [
    {"content": NEW[0], "layer": "L2_FACT", "tags": ["travel", "skiing"], "owner": "user"},
    {"content": NEW[1], "layer": "L2_FACT", "tags": ["relationship"], "owner": "user"},
    {"content": NEW[2], "layer": "L2_FACT", "tags": ["friends"], "owner": "agent"},
]


class TestFallbackAddOps:
    def test_builds_one_add_per_extracted_memory(self):
        ops = MemoryReconciler._fallback_add_ops(NEW, META)
        assert len(ops) == 3
        assert all(o.op == "ADD" for o in ops)
        assert [o.content for o in ops] == NEW

    def test_preserves_layer_tags_owner(self):
        """兜底不能把 meta 丢了，否则 owner/tags 全部退化。"""
        ops = MemoryReconciler._fallback_add_ops(NEW, META)
        assert [o.layer for o in ops] == ["L2_FACT"] * 3
        assert ops[0].tags == ["travel", "skiing"]
        assert ops[2].owner == "agent"

    def test_reason_marks_degradation(self):
        ops = MemoryReconciler._fallback_add_ops(NEW, META)
        assert "degraded" in ops[0].reason

    def test_works_without_meta(self):
        """meta 缺失时也要能兜底（只是没有 tags/owner）。"""
        ops = MemoryReconciler._fallback_add_ops(NEW, None)
        assert len(ops) == 3 and all(o.op == "ADD" for o in ops)

    def test_skips_empty_content(self):
        ops = MemoryReconciler._fallback_add_ops(["", None, "real fact"], None)
        assert [o.content for o in ops] == ["real fact"]

    def test_no_memories_yields_nothing(self):
        assert MemoryReconciler._fallback_add_ops([], None) == []


class TestReconcileResultDegradedFlag:
    def test_default_is_not_degraded(self):
        r = ReconcileResult()
        assert r.degraded is False and r.degraded_reason is None

    def test_degraded_result_still_succeeds(self):
        """关键语义：兜底后 success 必须为 True，否则 writer 仍会丢弃全部内容。

        writer 里是 `if not recon_result.success: return [], ...` —— 只要 success=False，
        ops 里有什么都不会落库。
        """
        r = ReconcileResult(
            ops=MemoryReconciler._fallback_add_ops(NEW, META),
            success=True, degraded=True, degraded_reason="LLM_UNAVAILABLE",
        )
        assert r.success is True and r.degraded is True
        assert len(r.ops) == 3


class TestWriterHonorsDegradedResult:
    def test_writer_stores_ops_when_success_true(self):
        """从 writer 源码上钉住：success=True 时不会走提前 return 的丢弃分支。"""
        import inspect

        from hy_memory.pipelines.writer import MemoryWriter

        src = inspect.getsource(MemoryWriter._reconcile_and_store_locked)
        assert "if not recon_result.success:" in src
        # 兜底路径必须可观测
        assert "degraded" in src


class TestLLMFailureIsNotPropagated:
    """LLM 异常不能冒泡 —— 冒泡会让整批抽取结果连带丢弃。"""

    def test_llm_call_is_wrapped(self):
        import inspect

        from hy_memory.agent.reconciler import MemoryReconciler as R

        src = inspect.getsource(R.reconcile)
        # llm.complete 必须在 try 内，且失败后走 ADD-all
        assert "_llm_error" in src
        assert "_fallback_add_ops" in src
        assert "LLM_UNAVAILABLE" in src

    def test_failure_log_tolerates_none_response(self):
        """LLM 挂掉时 response 是 None；失败分支里若直接取 response.prompt_tokens
        会抛 AttributeError，把兜底本身也废掉。"""
        import inspect

        from hy_memory.agent.reconciler import MemoryReconciler as R

        src = inspect.getsource(R.reconcile)
        # 只看失败分支（成功路径里 response 必然非 None，直接取属性是对的）
        start = src.index("if not _parse_ok:")
        end = src.index("_fallback_add_ops", start)
        fail_branch = src[start:end]
        assert 'getattr(response, "prompt_tokens", 0)' in fail_branch
        assert "response.prompt_tokens," not in fail_branch


class TestExtractorPromptRules:
    """新增的两条 extractor 规则（线上 badcase 直接对应）。"""

    def _prompts(self):
        from hy_memory.agent.extractor import EXTRACT_SYSTEM_PROMPT
        from hy_memory.agent import prompts_zh

        zh = next(
            v for k, v in vars(prompts_zh).items()
            if isinstance(v, str) and "时间规则" in v and "质量要求" in v
        )
        return EXTRACT_SYSTEM_PROMPT, zh

    def test_just_happened_events_rule_present_both_languages(self):
        """"我刚旅行回来" 的返回日期就是 LoCoMo 时序题的答案，此前被丢掉。"""
        en, zh = self._prompts()
        assert "just got back" in en
        assert "刚回来" in zh or "刚刚发生" in zh

    def test_no_generalisation_rule_present_both_languages(self):
        """Banff 被泛化成 "the Rocky Mountains"，具体地名丢失。"""
        en, zh = self._prompts()
        assert "Banff" in en and "Banff" in zh
        assert "Rocky Mountains" in en

    def test_cross_speaker_detail_rule_present(self):
        """细节由对方话轮给出、用户确认 —— 主体规则不该导致丢细节。"""
        en, zh = self._prompts()
        assert "other speaker" in en
        assert "对方话轮" in zh
