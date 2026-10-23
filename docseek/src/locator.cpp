#include "docseek/locator.h"

#include <algorithm>
#include <cmath>
#include <string>
#include <unordered_set>
#include <vector>

#include "docseek/query_parser.h"

namespace docseek {
namespace {

// 问句尾缀/疑问词补充检测：passageIntent 触发词表不含"在哪里/在哪/哪里"等
// 常见问句尾缀，这里补充识别，供 Locator 决定是否走问句召回放宽链路。
bool hasQuestionTail(const std::string& rawQuery) {
    if (rawQuery.find("在哪里") != std::string::npos) return true;
    if (rawQuery.find("在哪") != std::string::npos) return true;
    if (rawQuery.find("哪里") != std::string::npos) return true;
    size_t end = rawQuery.size();
    while (end > 0) {
        char c = rawQuery[end - 1];
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v') {
            --end;
        } else {
            break;
        }
    }
    if (end == 0) return false;
    auto endsWith = [&](const std::string& suffix) {
        return end >= suffix.size() &&
               rawQuery.compare(end - suffix.size(), suffix.size(), suffix) == 0;
    };
    if (endsWith("吗")) return true;
    if (rawQuery[end - 1] == '?') return true;
    if (endsWith("？")) return true;
    return false;
}

// PDF 页码辅助：路径是否为 .pdf（大小写不敏感）
bool hasPdfExt(const std::string& path) {
    if (path.size() < 4) return false;
    std::string ext = path.substr(path.size() - 4);
    for (char& c : ext) if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    return ext == ".pdf";
}

char lowerAscii(char c) {
    return (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : c;
}

// 是否为空白文本（空格/制表/换行/换页符等），用于丢弃 PDF 纯 '\f' 垃圾窗口
bool isBlankText(const std::string& t) {
    for (unsigned char c : t) {
        if (c != ' ' && c != '\t' && c != '\n' && c != '\r' && c != '\f' && c != '\v') return false;
    }
    return true;
}

// ASCII 大小写不敏感查找首个命中词位置（与 rankPassages 的匹配语义一致）
size_t findTermCi(const std::string& content, const std::string& term) {
    if (term.empty() || term.size() > content.size()) return std::string::npos;
    for (size_t i = 0; i + term.size() <= content.size(); ++i) {
        bool match = true;
        for (size_t j = 0; j < term.size(); ++j) {
            if (lowerAscii(content[i + j]) != lowerAscii(term[j])) { match = false; break; }
        }
        if (match) return i;
    }
    return std::string::npos;
}

// 按命中词字节偏移数换页符定页码（pdftotext 页间以 '\f' 分隔，页码 1-based）
int pdfPageForOffset(const std::string& content, size_t pos) {
    int page = 1;
    for (size_t i = 0; i <= pos && i < content.size(); ++i) {
        if (content[i] == '\f') ++page;
    }
    return page;
}

}  // namespace

namespace {

TermWeights buildTermWeights(Database& db, const ParsedQuery& pq) {
    TermWeights result;
    const int64_t N = db.docCount();
    std::unordered_set<std::string> seen;
    for (const auto& kw : pq.keywords) {
        std::string lower;
        lower.reserve(kw.size());
        for (char c : kw) {
            lower.push_back(lowerAscii(c));
        }
        if (!seen.insert(lower).second) {
            continue;
        }
        int64_t df = db.docFrequency(kw);
        if (df > N) {
            df = N;
        }
        double idf = std::log((N + 1.0) / (df + 1.0)) + 1.0;
        double weight = idf * termLengthWeight(kw);
        result.weights[lower] = weight;
    }
    return result;
}

}  // namespace

Locator::Locator(Database& db, Searcher& searcher)
    : db_(db), searcher_(searcher) {}

std::vector<Passage> Locator::locate(const std::string& rawQuery,
                                     const LocateOptions& opts) {
    std::vector<Passage> result;

    ParsedQuery pq = parseNaturalQuery(rawQuery);

    // 若解析后无词，退化为整串作为关键词。
    if (pq.keywords.empty() && pq.phrases.empty()) {
        // rawQuery 去空白后仍为空则直接返回。
        bool hasNonSpace = false;
        for (char c : rawQuery) {
            if (c != ' ' && c != '\t' && c != '\n' && c != '\r' && c != '\f' &&
                c != '\v') {
                hasNonSpace = true;
                break;
            }
        }
        if (!hasNonSpace) return result;
        pq.keywords.push_back(rawQuery);
    }

    // 拼接 recallQuery：keywords 与 phrases 共用去重集合，避免冗余 AND。
    std::string recallQuery;
    std::unordered_set<std::string> seenRecall;
    for (const auto& k : pq.keywords) {
        if (!seenRecall.insert(k).second) continue;
        if (!recallQuery.empty()) recallQuery.push_back(' ');
        recallQuery += k;
    }
    for (const auto& p : pq.phrases) {
        if (!seenRecall.insert(p).second) continue;
        if (!recallQuery.empty()) recallQuery.push_back(' ');
        recallQuery += p;
    }

    if (recallQuery.empty()) return result;

    const bool isQuestion = pq.passageIntent || hasQuestionTail(rawQuery);
    std::vector<Hit> hits = isQuestion
        ? searcher_.searchQuestion(recallQuery, opts.recallDocs)
        : searcher_.search(recallQuery, opts.recallDocs);

    std::vector<Passage> all;
    TermWeights termWeights = buildTermWeights(db_, pq);
    for (const auto& h : hits) {
        std::optional<std::string> content = db_.getContentById(h.doc_id);
        if (!content.has_value()) continue;
        std::vector<Passage> passages =
            rankPassages(h.doc_id, h.path, *content, pq, 3, termWeights, h.title);
        if (hasPdfExt(h.path)) {
            // rankPassages 返回的是滑动窗口，line_start 是窗口起点；
            // 页码按窗口内首个命中词在全文中的实际偏移定位；
            // 顺手丢弃纯换页符/空白的垃圾窗口（pdftotext 页间 '\f' 行不携带有效文本）
            for (auto it = passages.begin(); it != passages.end();) {
                if (isBlankText(it->text)) {
                    it = passages.erase(it);
                    continue;
                }
                if (!it->matched_terms.empty()) {
                    size_t pos = findTermCi(*content, it->matched_terms[0]);
                    it->page_no = (pos == std::string::npos) ? 1
                                                            : pdfPageForOffset(*content, pos);
                } else {
                    it->page_no = 1;
                }
                ++it;
            }
        }
        for (auto& p : passages) {
            all.push_back(std::move(p));
        }
    }

    std::sort(all.begin(), all.end(),
              [](const Passage& a, const Passage& b) {
                  if (a.score != b.score) return a.score > b.score;
                  return a.line_start < b.line_start;
              });

    if (opts.limit > 0 && static_cast<int>(all.size()) > opts.limit) {
        all.resize(opts.limit);
    }
    return all;
}

namespace {

// UTF-8 码点长度（1-4 字节），遇到非法首字节按 1 字节处理，避免死循环。
inline size_t utf8CharLen(unsigned char c) {
    if (c < 0x80) return 1;
    if ((c & 0xE0) == 0xC0) return 2;
    if ((c & 0xF0) == 0xE0) return 3;
    if ((c & 0xF8) == 0xF0) return 4;
    return 1;
}

// 向前推进 n 个 Unicode 码点，返回字节下标；若越界返回字符串长度。
inline size_t advanceChars(const std::string& s, size_t pos, size_t n) {
    size_t i = pos;
    while (i < s.size() && n > 0) {
        i += utf8CharLen(static_cast<unsigned char>(s[i]));
        --n;
    }
    return i > s.size() ? s.size() : i;
}

// 从 pos 向后回退 n 个 Unicode 码点，返回字节下标；若越界返回 0。
inline size_t retreatChars(const std::string& s, size_t pos, size_t n) {
    size_t i = pos;
    while (i > 0 && n > 0) {
        --i;
        // 回退到某个字符首字节（非 UTF-8 续字节 10xxxxxx）。
        while (i > 0 && (static_cast<unsigned char>(s[i]) & 0xC0) == 0x80) {
            --i;
        }
        --n;
    }
    return i;
}

// 在 context 内扫描所有匹配词的不重叠出现，ASCII 大小写不敏感，中文精确匹配。
// 返回按 start 升序的去重偏移列表。
std::vector<std::pair<int,int>> scanHighlights(
    const std::string& context, const std::vector<std::string>& terms) {
    std::vector<std::pair<int,int>> hits;
    for (const auto& term : terms) {
        if (term.empty()) continue;
        size_t pos = 0;
        while (pos + term.size() <= context.size()) {
            bool ok = true;
            for (size_t k = 0; k < term.size(); ++k) {
                unsigned char a = static_cast<unsigned char>(context[pos + k]);
                unsigned char b = static_cast<unsigned char>(term[k]);
                // ASCII 大小写不敏感；非 ASCII 字节精确比较（中文精确匹配）。
                if (a < 0x80 && b < 0x80) {
                    if (std::tolower(a) != std::tolower(b)) { ok = false; break; }
                } else if (a != b) {
                    ok = false;
                    break;
                }
            }
            if (ok) {
                hits.emplace_back(static_cast<int>(pos),
                                  static_cast<int>(pos + term.size()));
                pos += term.size();  // 不重叠
            } else {
                pos += utf8CharLen(static_cast<unsigned char>(context[pos]));
            }
        }
    }
    std::sort(hits.begin(), hits.end());
    hits.erase(std::unique(hits.begin(), hits.end()), hits.end());
    return hits;
}

}  // namespace

std::vector<PassageContext> Locator::locateWithContext(const std::string& rawQuery,
                                                       const LocateOptions& opts) {
    std::vector<Passage> anchors = locate(rawQuery, opts);
    std::vector<PassageContext> out;
    out.reserve(anchors.size());
    // 超长文档只取前 2MB 做锚点定位，避免全量扫描拖慢响应。
    constexpr size_t kMaxScan = 2 * 1024 * 1024;
    constexpr size_t kHalfWindow = 60;

    for (const auto& a : anchors) {
        PassageContext pc;
        pc.passage = a;

        std::optional<std::string> contentOpt = db_.getContentById(a.doc_id);
        if (!contentOpt.has_value() || contentOpt->empty()) {
            out.push_back(std::move(pc));
            continue;
        }
        std::string full = *contentOpt;
        if (full.size() > kMaxScan) {
            full.resize(kMaxScan);
        }

        // 找首个 matched_terms 在全文中的位置（ASCII 大小写不敏感，中文精确）。
        size_t anchorPos = std::string::npos;
        size_t anchorLen = 0;
        for (const auto& term : a.matched_terms) {
            if (term.empty()) continue;
            size_t p = findTermCi(full, term);
            if (p != std::string::npos) {
                anchorPos = p;
                anchorLen = term.size();
                break;
            }
        }

        if (anchorPos == std::string::npos) {
            // 无命中：取全文前 120 个 Unicode 字符作为 context，highlights 为空。
            size_t endPos = advanceChars(full, 0, 120);
            pc.context = full.substr(0, endPos);
            out.push_back(std::move(pc));
            continue;
        }

        size_t ctxStart = retreatChars(full, anchorPos, kHalfWindow);
        size_t ctxEnd = advanceChars(full, anchorPos + anchorLen, kHalfWindow);
        pc.context = full.substr(ctxStart, ctxEnd - ctxStart);

        // 在 context 内扫描全部 matched_terms 的不重叠出现。
        pc.highlights = scanHighlights(pc.context, a.matched_terms);
        out.push_back(std::move(pc));
    }
    return out;
}

}  // namespace docseek
