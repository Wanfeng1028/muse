#include "docseek/passage_ranker.h"

#include <algorithm>
#include <cctype>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

namespace docseek {
namespace {

constexpr int kMaxWindowLines = 6;
constexpr int kMaxWindowCodepoints = 400;
constexpr int kWindowStep = 3;

// 计算 UTF-8 码点数（非法字节按 1 推进，绝不死循环）。
int countUtf8Codepoints(const std::string& s) {
    int n = 0;
    size_t i = 0;
    while (i < s.size()) {
        unsigned char c = static_cast<unsigned char>(s[i]);
        size_t step = 1;
        if (c >= 0xF0 && c <= 0xF7) {
            step = 4;
        } else if (c >= 0xE0 && c <= 0xEF) {
            step = 3;
        } else if (c >= 0xC0 && c <= 0xDF) {
            step = 2;
        }
        i += step;
        ++n;
    }
    return n;
}

// ASCII 转小写；非 ASCII 字节原样保留。
std::string toLowerAscii(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (unsigned char c : s) {
        if (c < 0x80) {
            out.push_back(static_cast<char>(std::tolower(c)));
        } else {
            out.push_back(static_cast<char>(c));
        }
    }
    return out;
}

// 在 haystack（已小写）中查找 needle（已小写）出现次数。
int countOccurrences(const std::string& haystack, const std::string& needle) {
    if (needle.empty()) return 0;
    int count = 0;
    size_t pos = 0;
    while (pos < haystack.size()) {
        size_t found = haystack.find(needle, pos);
        if (found == std::string::npos) break;
        ++count;
        pos = found + needle.size();
    }
    return count;
}

// 查找 needle 首次出现位置；不存在返回 npos。
size_t findFirst(const std::string& haystack, const std::string& needle) {
    if (needle.empty()) return std::string::npos;
    return haystack.find(needle);
}

}  // namespace

std::vector<Passage> rankPassages(int64_t doc_id, const std::string& path,
                                  const std::string& content,
                                  const ParsedQuery& pq, int topK) {
    std::vector<Passage> result;
    if (topK <= 0) return result;
    if (content.empty()) return result;
    if (pq.keywords.empty() && pq.phrases.empty()) return result;

    // 切行：记录每行起始偏移。
    std::vector<std::pair<size_t, size_t>> lines;  // (start, end) 不含 '\n'
    {
        size_t start = 0;
        const size_t n = content.size();
        for (size_t i = 0; i <= n; ++i) {
            if (i == n || content[i] == '\n') {
                lines.emplace_back(start, i);
                start = i + 1;
            }
        }
    }
    const int lineCount = static_cast<int>(lines.size());
    if (lineCount == 0) return result;

    // 预处理关键词/短语小写形式。
    std::vector<std::string> kwLower;
    kwLower.reserve(pq.keywords.size());
    for (const auto& k : pq.keywords) kwLower.push_back(toLowerAscii(k));
    std::vector<std::string> phLower;
    phLower.reserve(pq.phrases.size());
    for (const auto& p : pq.phrases) phLower.push_back(toLowerAscii(p));

    const int totalKeywords = static_cast<int>(pq.keywords.size());

    // 滑动窗口。
    int windowIndex = 0;
    for (int wStart = 0; wStart < lineCount;) {
        // 强制断窗：行首为 '#' 的 markdown 标题行单独开启新窗口。
        // 若 wStart 行本身是标题行，它作为窗口首行；否则沿用累积。
        int wEnd = wStart;  // 含
        int accumulatedCodepoints = 0;
        int breakLine = -1;  // 触发断窗的标题行号；无断窗为 -1
        bool windowHasHeading = false;
        // 累积行直到超过上限。
        for (int li = wStart; li < lineCount; ++li) {
            if (li > wStart && (li - wStart) >= kMaxWindowLines) break;
            // 行内容。
            const auto& lr = lines[li];
            std::string lineText = content.substr(lr.first, lr.second - lr.first);
            int cps = countUtf8Codepoints(lineText);
            if (li > wStart && accumulatedCodepoints + cps > kMaxWindowCodepoints) {
                break;
            }
            accumulatedCodepoints += cps;
            wEnd = li;
            // markdown 标题行强制断窗（标题行本身开启新窗口）。
            bool isHeading = !lineText.empty() && lineText[0] == '#';
            if (li == wStart && isHeading) {
                windowHasHeading = true;
            }
            if (isHeading && li > wStart) {
                // 标题行不并入上一窗口。
                wEnd = li - 1;
                breakLine = li;
                break;
            }
        }
        if (wEnd < wStart) {
            ++windowIndex;
            if (breakLine >= 0) {
                wStart = breakLine;
            } else {
                wStart += kWindowStep;
            }
            continue;
        }

        // 构造窗口文本。
        std::string windowText;
        for (int li = wStart; li <= wEnd; ++li) {
            if (li > wStart) windowText.push_back('\n');
            const auto& lr = lines[li];
            windowText.append(content, lr.first, lr.second - lr.first);
        }
        std::string windowLower = toLowerAscii(windowText);

        // 计算命中。
        int uniqueKeywordHits = 0;
        int totalHits = 0;
        int phraseHitCount = 0;
        std::vector<std::pair<size_t, std::string>> matched;  // (pos, term)

        for (size_t ki = 0; ki < pq.keywords.size(); ++ki) {
            const std::string& lower = kwLower[ki];
            size_t pos = findFirst(windowLower, lower);
            if (pos != std::string::npos) {
                ++uniqueKeywordHits;
                int cnt = countOccurrences(windowLower, lower);
                totalHits += cnt;
                matched.emplace_back(pos, pq.keywords[ki]);
            }
        }
        for (size_t pi = 0; pi < pq.phrases.size(); ++pi) {
            const std::string& lower = phLower[pi];
            size_t pos = findFirst(windowLower, lower);
            if (pos != std::string::npos) {
                ++phraseHitCount;
                int cnt = countOccurrences(windowLower, lower);
                totalHits += cnt * 2;
                matched.emplace_back(pos, pq.phrases[pi]);
            }
        }

        double coverage =
            static_cast<double>(uniqueKeywordHits) /
            static_cast<double>(std::max(1, totalKeywords));
        double hitsTerm = std::min(1.0, static_cast<double>(totalHits) / 8.0);
        double phraseTerm =
            std::min(1.0, static_cast<double>(phraseHitCount) / 2.0);
        double posTerm = 1.0 / (1.0 + 0.1 * static_cast<double>(windowIndex));
        double score =
            0.5 * coverage + 0.3 * hitsTerm + 0.15 * phraseTerm + 0.05 * posTerm;

        if (pq.passageIntent && windowHasHeading) score += 0.1;

        if (score > 0.0) {
            Passage p;
            p.doc_id = doc_id;
            p.path = path;
            p.line_start = wStart + 1;
            p.line_end = wEnd + 1;
            p.text = windowText;
            p.score = score;

            // matched_terms 按首次出现位置排序、去重。
            std::sort(matched.begin(), matched.end(),
                      [](const std::pair<size_t, std::string>& a,
                         const std::pair<size_t, std::string>& b) {
                          if (a.first != b.first) return a.first < b.first;
                          return a.second < b.second;
                      });
            std::unordered_set<std::string> seenTerms;
            for (const auto& m : matched) {
                if (seenTerms.insert(m.second).second) {
                    p.matched_terms.push_back(m.second);
                }
            }
            result.push_back(std::move(p));
        }
        ++windowIndex;
        if (breakLine >= 0) {
            wStart = breakLine;
        } else {
            wStart += kWindowStep;
        }
    }

    // 排序：score 降序，line_start 升序 tie-break。
    std::sort(result.begin(), result.end(),
              [](const Passage& a, const Passage& b) {
                  if (a.score != b.score) return a.score > b.score;
                  return a.line_start < b.line_start;
              });

    if (static_cast<int>(result.size()) > topK) {
        result.resize(topK);
    }
    return result;
}

}  // namespace docseek
