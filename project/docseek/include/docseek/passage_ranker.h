#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
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

// 词长权重：1 个 Unicode 码点→0.35，2 个→0.7，3 个及以上→1.0。
// 依据：单字中文词（如"算/能/点"）噪声大、信息量低，应降权；
// 双字词半权；三字及以上完整概念词全权。
double termLengthWeight(const std::string& term);

// 词级权重表：键为小写词面，值为 idf 与词长权重的乘积。
struct TermWeights {
    std::unordered_map<std::string, double> weights;  // 键：小写词面
    double weightOf(const std::string& lowerTerm) const;  // 缺失键返回 1.0
};

// 在单篇文档内滑动窗口打分，返回 topK 段落（score 降序，line_start 升序 tie-break）。
std::vector<Passage> rankPassages(int64_t doc_id, const std::string& path,
                                  const std::string& content,
                                  const ParsedQuery& pq, int topK);

// 加权版本：coverage 与 hitsTerm 按 weights 的词权重计算；
// 缺失键按 1.0。全权重为 1.0 时分数与 5 参数版本逐位相同。
std::vector<Passage> rankPassages(int64_t doc_id, const std::string& path,
                                  const std::string& content,
                                  const ParsedQuery& pq, int topK,
                                  const TermWeights& weights);
// 标题信号版本：title 为文档标题（如 HTML <title>）；另自动取 content 首行
// markdown '# ' 标题行作补充标题源。query 关键词在任一标题中字面命中时，
// 按 kTitleTermBonus * 词权重给文档级加成（该文档全部窗口同享）；同一词在
// 两处同时命中只计一次。title 为空串时退化为无标题信号。
std::vector<Passage> rankPassages(int64_t doc_id, const std::string& path,
                                  const std::string& content,
                                  const ParsedQuery& pq, int topK,
                                  const TermWeights& weights,
                                  const std::string& title);

// 带原文前后文的定位结果：context 是命中词首次出现位置前后各 60 个 Unicode
// 字符的原文窗口（UTF-8 安全，不截断多字节字符）；highlights 是 matched_terms
// 在 context 内的全部不重叠出现位置，字节偏移 [start, end)，按 start 升序。
struct PassageContext {
    Passage passage;
    std::string context;
    std::vector<std::pair<int,int>> highlights;
};

}  // namespace docseek
