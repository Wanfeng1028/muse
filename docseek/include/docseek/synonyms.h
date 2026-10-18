// docseek 同义词表（最小可用版本，v0.16.0）
// 用途：为查询侧提供极少量、经 corpus 证据确认的 token 展开，
// 仅覆盖 B 类失败中"查询词与期望文档用词完全不含"的 3 组映射。
// 约束：精确匹配；未命中返回 nullptr，调用方必须保持原行为不变。
#pragma once

#include <cstddef>

namespace docseek {

struct SynonymEntry {
    const char* term;
    const char* const* expansions;
    int expansionCount;
};

// 精确匹配 term；命中返回条目指针，否则返回 nullptr。
const SynonymEntry* findSynonyms(const char* term);

}  // namespace docseek
