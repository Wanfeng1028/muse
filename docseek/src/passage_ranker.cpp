#include "docseek/passage_ranker.h"
#include "docseek/synonyms.h"

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

// 复合短语加成权重；取值依据：大于位置项（0.05）、小于覆盖度主项（0.5）；
// 实测 v07-024：主题文档 0.688+0.25=0.938 > 干扰文档 0.845。
constexpr double kCompoundPhraseBonus = 0.25;
// 数值范围答案加成：当问句索取数值范围/数量，且窗口同时含阿拉伯数字与紧邻计量单位时，
// 视为该窗口承载了可量化的答案，故对排序给固定加成。适用于可被“数字+单位”直接回答的问句；
// 边界与局限：加成是固定值，不随命中数字或单位个数变化；对无单位、单位与数字不相邻、
// 或答案以文字数词表达的情形不触发。
constexpr double kRangeAnswerBonus = 0.08;
constexpr double kSynonymHitBonus = 0.08;  // 同义词命中加成：query 词以同义词变体在窗口命中时，视为概念级相关信号，对排序给固定加成。适用于同义词表可覆盖的查询词；边界与局限：加成是固定值，不随命中次数或同义词距离变化；触发词表是字面枚举，未登录的同义表达不触发。
// 标题信号加成（v0.25.0）：query 关键词在文档标题（传入的 title，如 HTML <title>）
// 或 content 首行 markdown 标题中字面出现时，视为文档级主题信号，对该文档全部
// 窗口给固定加成。取值依据：与 passageIntent 标题行加成（0.1）同量级；仅按词长
// 权重 termLengthWeight 缩放（单字 0.35/双字 0.7/三字+ 1.0）——单字噪声词自然降权。
// 不乘 idf：idf 已在段落级 coverage/hitsTerm 的 weights 中体现；标题先验只打断
// 平局、不压倒段落证据（v0.25.0 初版用 weightOf 致加成可达 1.4+，评测 -29，已修正）。
constexpr double kTitleTermBonus = 0.1;
// 稀有词命中加成（v0.26.0）：idf>=6.2 约对应 960 文档中 df<=4 的关键词；
// 阈值取 6.2 而非 6.0：df=5 的词（如"青旅"idf=6.08）在主题聚类语料里常为主题词
// 而非查询区分词——v09-t048-q09 实测其加成把厨房礼仪段落推过了直接答案（去走廊），
// 故收紧到 df<=4；"继承"(df=3,idf=6.48) 等真超稀有词不受影响。
// 触发条件为 kwHit 的字面认领 span，不含同义词变体；量级与 0.08 加成家族同量级，
// 单个超稀有词 +0.05 后得分即可超过两个常见词；对同一窗口累计加成封顶，防止长查询
// 中多个稀有词叠加后失控。
constexpr double kRareTermIdfThreshold = 6.2;
constexpr double kRareTermBonus = 0.05;
constexpr double kRareTermBonusCap = 0.15;
// 复现结构对齐加成（v0.27.0）：当查询本身具有"过去状态→近期复现"结构
// （pq.hasRecurrence，由 query_parser 的 detectRecurrence 设置）且当前窗口同时含
// 过去状态标记与复现标记时，视为窗口在复现叙事结构上与查询对齐，给固定加成。
// 适用：复现型问句（"本来已经X，最近又Y"）的段落排序；
// 边界与局限：加成是固定值，只看标记共现、不看语义角色；触发词表是字面枚举的闭集
// （与 src/query_parser.cpp 的 detectRecurrence 保持一致），未登录的复现表达不触发。
constexpr double kRecurrenceAlignBonus = 0.08;

// 取 content 首个非空行的 markdown 标题文本：剥离行首全部 '#' 与空白后返回；
// 首个非空行不是标题行（行首非 '#'）时返回空串。用于 .md 文档补充标题信号
// （其 DB title 为文件名 stem、无语义）；HTML 文档标题由调用方经 title 参数传入。
std::string firstMarkdownHeading(const std::string& content) {
    size_t i = 0;
    const size_t n = content.size();
    while (i < n) {
        size_t eol = content.find('\n', i);
        if (eol == std::string::npos) eol = n;
        size_t s = i;
        while (s < eol && (content[s] == ' ' || content[s] == '\t' || content[s] == '\r')) ++s;
        if (s < eol) {
            size_t t = s;
            while (t < eol && content[t] == '#') ++t;
            if (t == s) return "";
            while (t < eol && (content[t] == ' ' || content[t] == '\t')) ++t;
            return content.substr(t, eol - t);
        }
        i = eol + 1;
    }
    return "";
}

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

double termLengthWeight(const std::string& term) {
    std::size_t count = 0;
    std::size_t i = 0;
    while (i < term.size()) {
        unsigned char c = static_cast<unsigned char>(term[i]);
        if (c < 0x80) {
            i += 1;
        } else if ((c >> 5) == 0x6) {
            if (i + 1 < term.size() && (static_cast<unsigned char>(term[i + 1]) >> 6) == 0x2) {
                i += 2;
            } else {
                i += 1;
            }
        } else if ((c >> 4) == 0xE) {
            if (i + 2 < term.size() && (static_cast<unsigned char>(term[i + 1]) >> 6) == 0x2 && (static_cast<unsigned char>(term[i + 2]) >> 6) == 0x2) {
                i += 3;
            } else {
                i += 1;
            }
        } else if ((c >> 3) == 0x1E) {
            if (i + 3 < term.size() && (static_cast<unsigned char>(term[i + 1]) >> 6) == 0x2 && (static_cast<unsigned char>(term[i + 2]) >> 6) == 0x2 && (static_cast<unsigned char>(term[i + 3]) >> 6) == 0x2) {
                i += 4;
            } else {
                i += 1;
            }
        } else {
            i += 1;
        }
        ++count;
    }
    if (count == 0 || count == 1) {
        return 0.35;
    } else if (count == 2) {
        return 0.7;
    } else {
        return 1.0;
    }
}

double TermWeights::weightOf(const std::string& lowerTerm) const {
    auto it = weights.find(lowerTerm);
    if (it != weights.end()) {
        return it->second;
    }
    return 1.0;
}

std::vector<Passage> rankPassages(int64_t doc_id, const std::string& path,
                                  const std::string& content,
                                  const ParsedQuery& pq, int topK,
                                  const TermWeights& weights,
                                  const std::string& title) {
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

    // 标题信号（v0.25.0）：文档级主题先验，计算一次、该文档全部窗口同享。
    // 命中判定：kwLower 在 titleLower 或 headingLower 中的字面出现；同一词在
    // 两处同时出现只计一次。glue 词已在 query_parser 层剔除出 keywords；
    // 仅按词长权重缩放（不用 weights：idf 已在段落级计分中体现）。
    double titleBonus = 0.0;
    {
        const std::string titleLower = toLowerAscii(title);
        const std::string headingLower = toLowerAscii(firstMarkdownHeading(content));
        for (size_t ki = 0; ki < kwLower.size(); ++ki) {
            const std::string& lower = kwLower[ki];
            if (lower.empty()) continue;
            const bool inTitle = !titleLower.empty() &&
                                 titleLower.find(lower) != std::string::npos;
            const bool inHeading = !headingLower.empty() &&
                                   headingLower.find(lower) != std::string::npos;
            if (inTitle || inHeading) {
                titleBonus += kTitleTermBonus * termLengthWeight(pq.keywords[ki]);
            }
        }
    }

    // 复合短语候选集（两路并集）：
    // ① 全关键词按序拼接（历史行为）：短查询的全部关键词拼接后若在窗口连续出现，
    // 是强主题信号；长拼接串几乎永不连续出现，自然失效，不引入误触发。
    // ② 理解层重构的复合概念（如方位时间结构还原时\"还原词+其后紧邻 token\"
    // 构成的深层相邻二元组）：连续出现是比词袋更强的意图信号
    // （与 Searcher 文档级的 phraseBoost 同原理）。
    // 表层相邻关键词二元组误触发率高（如否定词+动词在无关文档偶然相邻），不采用。
    // 每个候选非空、且不同于任一引号短语时生效（引号短语已有 phraseTerm 加成，
    // 避免重复）；去重后保留。
    std::vector<std::string> queryCompounds;
    auto tryAddCompound = [&](const std::string& raw) {
        std::string c = toLowerAscii(raw);
        if (c.empty()) return;
        for (const auto& p: phLower) { if (c == p) return;}
        for (const auto& q: queryCompounds) { if (c == q) return;}
        queryCompounds.push_back(c);
    };
    if (kwLower.size() >= 2) {
        std::string full;
        for (const auto& k: kwLower) full += k;
        tryAddCompound(full);
    }
    for (const auto& rc: pq.reconstructedCompounds) {
        tryAddCompound(rc);
    }




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
        double uniqueHitWeight = 0;
        double totalHitsWeighted = 0;
        int phraseHitCount = 0;
        std::vector<std::pair<size_t, std::string>> matched;  // (pos, term)

        bool synonymFired = false;
        // 重叠感知计分（v0.24.0）：jieba CutForSearch 会把复合词展开成重叠关键词
        // （如"过敏反应"→"过敏"+"反应"+"过敏反应"）。旧逻辑对同一文本 span
        // 重复计分，导致错误文档靠三重计分反超（v09-t173-q11 实测：错误文档
        // uniqueHitWeight 14.28 > 期望文档 14.24）。
        // 新逻辑：枚举每个关键词的全部字面命中 span，按 span 长度降序贪心认领
        // 字节区间——重叠区间只归最长者；关键词有 >=1 个被认领 span 即计入
        // uniqueHitWeight，被认领 span 个数计入 totalHitsWeighted。
        // 同义词回退语义与旧逻辑一致：字面零命中才试同义词，只补
        // uniqueHitWeight、不计 totalHitsWeighted，matched_terms 记原 query 词。
        struct KwSpan {
            size_t start;
            size_t end;  // 不含
            size_t ki;
        };
        std::vector<KwSpan> kwSpans;
        kwSpans.reserve(pq.keywords.size() * 4);
        std::vector<size_t> kwFirstClaimedPos(pq.keywords.size(), std::string::npos);
        std::vector<char> kwSynonymHit(pq.keywords.size(), 0);
        std::vector<size_t> kwSynonymPos(pq.keywords.size(), std::string::npos);
        for (size_t ki = 0; ki < pq.keywords.size(); ++ki) {
            const std::string& lower = kwLower[ki];
            const size_t spansBefore = kwSpans.size();
            if (!lower.empty()) {
                size_t from = 0;
                while (from < windowLower.size()) {
                    const size_t found = windowLower.find(lower, from);
                    if (found == std::string::npos) break;
                    kwSpans.push_back(KwSpan{found, found + lower.size(), ki});
                    from = found + lower.size();
                }
            }
            if (kwSpans.size() == spansBefore) {
                size_t pos = std::string::npos;
                if (const SynonymEntry* e = findSynonyms(pq.keywords[ki].c_str())) {
                    for (int k = 0; k < e->expansionCount && pos == std::string::npos; ++k) {
                        pos = findFirst(windowLower, toLowerAscii(e->expansions[k]));
                        if (pos != std::string::npos) {
                            synonymFired = true;
                        }
                    }
                }
                if (pos != std::string::npos) {
                    kwSynonymHit[ki] = 1;
                    kwSynonymPos[ki] = pos;
                }
            }
        }
        std::sort(kwSpans.begin(), kwSpans.end(),
                  [](const KwSpan& a, const KwSpan& b) {
                      const size_t lena = a.end - a.start;
                      const size_t lenb = b.end - b.start;
                      if (lena != lenb) return lena > lenb;
                      return a.ki < b.ki;
                  });
        std::vector<char> kwHit(pq.keywords.size(), 0);
        std::vector<std::pair<size_t, size_t>> claimed;
        claimed.reserve(kwSpans.size());
        for (size_t si = 0; si < kwSpans.size(); ++si) {
            const KwSpan& s = kwSpans[si];
            bool overlap = false;
            for (size_t ci = 0; ci < claimed.size(); ++ci) {
                if (s.start < claimed[ci].second && claimed[ci].first < s.end) {
                    overlap = true;
                    break;
                }
            }
            if (overlap) continue;
            claimed.emplace_back(s.start, s.end);
            kwHit[s.ki] = 1;
            totalHitsWeighted += weights.weightOf(kwLower[s.ki]);
            if (kwFirstClaimedPos[s.ki] == std::string::npos ||
                s.start < kwFirstClaimedPos[s.ki]) {
                kwFirstClaimedPos[s.ki] = s.start;
            }
        }
        double rareTermBonus = 0.0;
        for (size_t ki = 0; ki < pq.keywords.size(); ++ki) {
            if (kwHit[ki]) {
                uniqueHitWeight += weights.weightOf(kwLower[ki]);
                matched.emplace_back(kwFirstClaimedPos[ki], pq.keywords[ki]);
                auto itw = weights.weights.find(kwLower[ki]);
                if (itw != weights.weights.end()) {
                    double idf = itw->second / termLengthWeight(pq.keywords[ki]);
                    if (idf >= kRareTermIdfThreshold) rareTermBonus += kRareTermBonus;
                }
            } else if (kwSynonymHit[ki]) {
                uniqueHitWeight += weights.weightOf(kwLower[ki]);
                matched.emplace_back(kwSynonymPos[ki], pq.keywords[ki]);
            }
        }
        for (size_t pi = 0; pi < pq.phrases.size(); ++pi) {
            const std::string& lower = phLower[pi];
            size_t pos = findFirst(windowLower, lower);
            if (pos != std::string::npos) {
                ++phraseHitCount;
                int cnt = countOccurrences(windowLower, lower);
                totalHitsWeighted += cnt * 2;
                matched.emplace_back(pos, pq.phrases[pi]);
            }
        }

        double kwWeightSum = 0.0;
        for (const auto& k : kwLower) kwWeightSum += weights.weightOf(k);
        double coverage = uniqueHitWeight / std::max(1.0, kwWeightSum);
        double hitsTerm = std::min(1.0, totalHitsWeighted / 8.0);
        double phraseTerm =
            std::min(1.0, static_cast<double>(phraseHitCount) / 2.0);
        double posTerm = 1.0 / (1.0 + 0.1 * static_cast<double>(windowIndex));
        double score =
            0.5 * coverage + 0.3 * hitsTerm + 0.15 * phraseTerm + 0.05 * posTerm;
        score += titleBonus;  // v0.25.0 标题信号：文档级先验，全部窗口同享
        if (rareTermBonus > kRareTermBonusCap) rareTermBonus = kRareTermBonusCap;
        score += rareTermBonus;  // v0.26.0 稀有词命中加成

        // v0.27.0 复现结构对齐：查询有复现结构、且窗口同时含两类标记时加成一次。
        if (pq.hasRecurrence) {
            static const std::vector<std::string> kPast = {
                "已经", "曾经", "本来", "原本", "以前", "过去"};
            static const std::vector<std::string> kRecur = {
                "又", "再次", "重新", "反复", "再度", "突然", "忽然"};
            bool hasPast = false, hasRecur = false;
            for (const auto& t : kPast) {
                if (windowLower.find(t) != std::string::npos) { hasPast = true; break; }
            }
            for (const auto& t : kRecur) {
                if (windowLower.find(t) != std::string::npos) { hasRecur = true; break; }
            }
            if (hasPast && hasRecur) score += kRecurrenceAlignBonus;
        }

        if (pq.passageIntent && windowHasHeading) score += 0.1;

// 复合短语加成：窗口原文连续包含任一候选二元组即触发一次（不叠加）。
for (const auto& qc: queryCompounds) {
    if (windowLower.find(qc)!= std::string::npos) {
        score += kCompoundPhraseBonus;
        break;
    }
}

        // 数值范围答案加成：query 含范围类疑问词，且窗口含“阿拉伯数字+紧邻单位”。
        {
            bool queryAsksRange = false;
            {
                std::string queryJoined;
                for (const auto& kw : pq.keywords) queryJoined += kw;
                std::transform(queryJoined.begin(), queryJoined.end(), queryJoined.begin(),
                               [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
                static const char* kRangeHints[] = {"范围", "多少", "多久", "多长", "多大",
                                                    "几", "多高", "多宽", "多厚"};
                for (const char* hint : kRangeHints) {
                    if (queryJoined.find(hint) != std::string::npos) {
                        queryAsksRange = true;
                        break;
                    }
                }
            }
            if (queryAsksRange) {
                static const std::string kUnits[] = {"毫米", "厘米", "mm", "cm", "米", "寸",
                                                     "英寸", "克", "kg", "分钟", "小时", "秒"};
                int hitCount = 0;
                for (std::size_t i = 0; i < windowLower.size(); ++i) {
                    if (windowLower[i] < '0' || windowLower[i] > '9') continue;
                    std::size_t j = i;
                    while (j < windowLower.size() &&
                           ((windowLower[j] >= '0' && windowLower[j] <= '9') || windowLower[j] == '.')) {
                        ++j;
                    }
                    for (const std::string& u : kUnits) {
                        if (windowLower.compare(j, u.size(), u) == 0) {
                            ++hitCount;
                            break;
                        }
                    }
                    i = j;
                }
                // 范围答案常给上下界，要求至少 2 个数值+单位，排除“1毫米”这类单点提及
                if (hitCount >= 2) score += kRangeAnswerBonus;
            }
        }

        // 同义词命中加成：文档用变体词回应 query 概念是强相关信号。
        if (synonymFired) score += kSynonymHitBonus;

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

std::vector<Passage> rankPassages(int64_t doc_id, const std::string& path,
                                  const std::string& content,
                                  const ParsedQuery& pq, int topK) {
    return rankPassages(doc_id, path, content, pq, topK, TermWeights{}, "");
}

std::vector<Passage> rankPassages(int64_t doc_id, const std::string& path,
                                  const std::string& content,
                                  const ParsedQuery& pq, int topK,
                                  const TermWeights& weights) {
    return rankPassages(doc_id, path, content, pq, topK, weights, "");
}

}  // namespace docseek
