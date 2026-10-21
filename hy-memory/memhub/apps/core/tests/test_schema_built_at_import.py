"""模型的 schema 必须在 import 时建好，不能拖到运行时在事件循环上建。

pydantic 遇到前向引用时会把核心 schema 留着不建，等第一次用到再现场生成。
那个「第一次」通常发生在第一个请求上，也就是事件循环上；生成过程会走进
inspect.signature → tokenize，真机 core.log 第 1973 行的 watchdog dump 里
MainThread 就正卡在这条路径上。

所以这条守卫不看耗时（耗时会随机器抖动），只看一个确定性的事实：
import 完之后，还有没有模型的 schema 是没建完的。
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

import pydantic

import one_memory


def _every_model() -> list[type[pydantic.BaseModel]]:
    unimportable: list[str] = []
    for info in pkgutil.walk_packages(one_memory.__path__, "one_memory."):
        try:
            importlib.import_module(info.name)
        except ImportError:
            # 可选依赖缺席是已知情况。除此之外的失败必须报出来：
            # 悄悄跳过一个模块，正好会把它里面那个不完整的模型一起藏掉。
            unimportable.append(info.name)
    assert not unimportable, f"这些模块 import 失败，里面的模型没有被检查到：{sorted(unimportable)}"
    seen: dict[str, type[pydantic.BaseModel]] = {}
    for name, module in list(sys.modules.items()):
        if not name.startswith("one_memory"):
            continue
        for attribute in vars(module).values():
            if (
                isinstance(attribute, type)
                and issubclass(attribute, pydantic.BaseModel)
                and attribute.__module__.startswith("one_memory")
            ):
                seen[f"{attribute.__module__}.{attribute.__qualname__}"] = attribute
    return list(seen.values())


def test_every_model_has_its_schema_built_before_the_first_request():
    models = _every_model()
    # 先证明这把尺子确实量到了东西，否则「没有不完整的模型」可能只是
    # 因为压根没收集到模型 —— 那样这条守卫永远绿。
    assert len(models) > 100, f"只收集到 {len(models)} 个模型，守卫没在量真东西"

    deferred = sorted(
        f"{model.__module__}.{model.__qualname__}"
        for model in models
        if not model.__pydantic_complete__
    )
    assert not deferred, (
        "这些模型的 schema 要等到第一次使用才生成，那一次很可能在事件循环上："
        f"{deferred}。在定义完前向引用指向的类之后调用 model_rebuild() 即可。"
    )
