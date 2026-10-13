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
};

// 在单篇文档内滑动窗口打分，返回 topK 段落（score 降序，line_start 升序 tie-break）。
std::vector<Passage> rankPassages(int64_t doc_id, const std::string& path,
                                  const std::string& content,
                                  const ParsedQuery& pq, int topK);

}  // namespace docseek
