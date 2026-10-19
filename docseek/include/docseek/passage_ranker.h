#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "docseek/query_parser.h"

namespace docseek {

// 段落级定位结果。
struct Passage {
    int64_t doc_id = 0;
    std::string path;
    int line_start = 1;   // 1-based
    int line_end = 1;     // 1-based，含
    std::string text;     // 窗口原文（行间用 '\n' 连接）
    double score = 0;
    std::vector<std::string> matched_terms;  // 按首次出现序，去重
    int page_no = 0;  // PDF 文档的页码（1-based）；非 PDF 为 0（不适用）
};

// 在单篇文档内滑动窗口打分，返回 topK 段落（score 降序，line_start 升序 tie-break）。
std::vector<Passage> rankPassages(int64_t doc_id, const std::string& path,
                                  const std::string& content,
                                  const ParsedQuery& pq, int topK);

// 带原文前后文的定位结果：context 是命中词首次出现位置前后各 60 个 Unicode
// 字符的原文窗口（UTF-8 安全，不截断多字节字符）；highlights 是 matched_terms
// 在 context 内的全部不重叠出现位置，字节偏移 [start, end)，按 start 升序。
struct PassageContext {
    Passage passage;
    std::string context;
    std::vector<std::pair<int,int>> highlights;
};

}  // namespace docseek
