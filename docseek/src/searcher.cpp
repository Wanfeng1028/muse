#include "docseek/searcher.h"

#include "docseek/token_locate.h"

#include "docseek/query_parser.h"
#include "docseek/synonyms.h"
#include "docseek/jieba_tokenizer.h"

#include <algorithm>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>
#include <cctype>

namespace docseek {
namespace {
// 单 token 全停用词判断："的了在了"这类无空白单 token，CutForSearch 切出
// [的,了,在,了] 全是单字停用词时，视为纯停用词查询（GAP-STOPWORD-001 补强）。
bool isAllStopwordsToken(const std::string& token) {
    if (token.empty()) return false;
    if (isSingleCharStopword(token)) return true;
    std::vector<std::string> words;
    if (const cppjieba::Jieba* jieba = jiebaInstance()) {
        jieba->CutForSearch(token, words);
    }
    if (words.empty()) return false;
    for (const auto& w : words) {
        if (!isSingleCharStopword(w)) return false;
    }
    return true;
}


// 统计 UTF-8 码点个数，并判断是否为"单个 CJK 码点"（用于单字前缀查询）。
// 只在 searcher.cpp 匿名 namespace 内使用，不依赖 query_parser.cpp 的内部函数。
bool isSingleCjkCodepoint(const std::string& token) {
    size_t codepoints = 0;
    bool cjk = false;
    for (size_t i = 0; i < token.size();) {
        unsigned char c = static_cast<unsigned char>(token[i]);
        size_t len = 1;
        if ((c & 0x80) == 0x00) {
            len = 1;
        } else if ((c & 0xE0) == 0xC0) {
            len = 2;
        } else if ((c & 0xF0) == 0xE0) {
            len = 3;
        } else if ((c & 0xF8) == 0xF0) {
            len = 4;
        } else {
            return false;  // 非法 UTF-8 首字节，保守放弃前缀
        }
        if (i + len > token.size()) return false;
        ++codepoints;
        if (codepoints > 1) return false;
        // CJK 统一表意文字基本区 U+4E00..U+9FFF（UTF-8: E4B880..E9BFBF）。
        if (len == 3 && c >= 0xE4 && c <= 0xE9) {
            unsigned int cp = ((c & 0x0F) << 12) |
                              ((static_cast<unsigned char>(token[i + 1]) & 0x3F) << 6) |
                              (static_cast<unsigned char>(token[i + 2]) & 0x3F);
            if (cp >= 0x4E00 && cp <= 0x9FFF) cjk = true;
        }
        i += len;
    }
    return codepoints == 1 && cjk;
}

// 将单个 token 用双引号包裹，内部的双引号转义为两个双引号（FTS5 字符串字面量规则）。
std::string quoteToken(const std::string& token) {
    std::string out;
    out.reserve(token.size() + 2);
    out.push_back('"');
    for (char c : token) {
        if (c == '"') {
            out.push_back('"');  // FTS5 中双引号转义为两个双引号
        }
        out.push_back(c);
    }
    out.push_back('"');
    return out;
}

// 按空白切分查询，得到原始 token 列表。
std::vector<std::string> splitTokens(const std::string& query) {
    std::vector<std::string> tokens;
    std::string cur;
    for (char c : query) {
        // 空白字符（空格、制表、换行等）作为分隔符。
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v') {
            if (!cur.empty()) {
                tokens.push_back(cur);
                cur.clear();
            }
        } else {
            cur.push_back(c);
        }
    }
    if (!cur.empty()) {
        tokens.push_back(cur);
    }
    return tokens;
}

// 去掉查询中所有空白，得到连续子串（用于短语加成）。
std::string removeWhitespace(const std::string& query) {
    std::string out;
    out.reserve(query.size());
    for (char c : query) {
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v') {
            continue;
        }
        out.push_back(c);
    }
    return out;
}

}  // namespace

Searcher::Searcher(Database& db) : db_(db) {}

Searcher::Searcher(Database& db, SearchWeights weights) : db_(db), weights_(weights) {}

void Searcher::setWeights(SearchWeights weights) {
    weights_ = weights;
}

SearchWeights Searcher::weights() const {
    return weights_;
}


// 把单个查询词展开为 FTS5 查询片段。
//
// CutForSearch 的输出分两种关系，必须区别对待：
//  1. 同一起始位置的重叠词（如"咖啡豆"=><咖啡@0><咖啡豆@0>）是同一文本的
//     不同切分：放在单个引号串里会被 FTS5 当成短语（要求相邻，恒为 0），
//     必须 OR 起来；
//  2. 不同起始位置的词（如<超导@0><材料@6><制备@12>）是顺序关系：保持 AND。
// FTS5 语法要求括号 OR 组与其他部分必须显式 AND 连接。
//
// 词的起始位置用与 jiebaXTokenize 相同的"全文 occurrence 扫描 + 已认领集合"
// 定位，保证查询侧与索引侧一致。任一词定位失败则退化为 quoteToken(token)。
std::string expandTokenWithJoiner(const std::string& token, const std::string& joiner) {
    std::vector<std::string> words;
    const cppjieba::Jieba* jieba = jiebaInstance();
    if (jieba != nullptr) {
        try {
            jieba->CutForSearch(token, words);
        } catch (...) {
            words.clear();
        }
    }

    // 定位逻辑来自 docseek/token_locate.h（与 jiebaXTokenize 一致）。
    // 按起始字节偏移分组（std::map 自动按 key 排序）。
    std::set<std::pair<std::string, size_t>> claimed;
    std::vector<LocatedToken> located = claimTokenPositions(token, words, claimed);
    // Fix A：认领失败不再整串退化。用认领成功的词继续构造分组；
    // 未被认领的词各自退化为 quoteToken(w) 并 AND 追加。
    std::set<std::string> claimedWords;
    for (const LocatedToken& lt : located) claimedWords.insert(lt.word);
    std::vector<std::string> unclaimed;
    for (const std::string& w : words) {
        if (w.empty()) continue;
        if (claimedWords.find(w) == claimedWords.end() &&
            std::find(unclaimed.begin(), unclaimed.end(), w) == unclaimed.end()) {
            unclaimed.push_back(w);
        }
    }

    std::map<size_t, std::vector<std::string>> groups;
    for (const LocatedToken& lt : located) {
        std::vector<std::string>& g = groups[lt.byteOffset];
        if (std::find(g.begin(), g.end(), lt.word) == g.end()) {
            g.push_back(lt.word);
        }
    }

    // 同义词展开（B3-r2）：组内每个词精确查同义词表，命中的 expansions 并入同一 OR 组。
    // 中文查询多为无空白单 token，词组级是唯一能命中表内词的层级；
    // 仅当组内出现表内词时激活，其余情况行为与原来一字不差。
    for (auto& kv : groups) {
        std::vector<std::string>& g = kv.second;
        std::vector<std::string> extra;
        for (const std::string& w : g) {
            const SynonymEntry* e = findSynonyms(w.c_str());
            if (e == nullptr) continue;
            for (int k = 0; k < e->expansionCount; ++k) {
                std::string ex(e->expansions[k]);
                if (std::find(g.begin(), g.end(), ex) == g.end() &&
                    std::find(extra.begin(), extra.end(), ex) == extra.end()) {
                    extra.push_back(ex);
                }
            }
        }
        g.insert(g.end(), extra.begin(), extra.end());
    }
    if (groups.empty() && unclaimed.empty()) {
        return quoteToken(token);
    }

    // 把一组词转成查询片段：单成员直接引号，多成员 OR。
    // 单个 CJK 码点且非停用词时改用 FTS5 前缀查询 "X"*（星号在右引号之外），
    // 因为 jieba CutForSearch 的 query 侧与索引侧切分常对不上，单字精确查
    // 会漏掉以该字为前缀的词（如"进"漏"进站"）。多字词/ASCII 词/单字停用词保持精确。
    auto wordExpr = [](const std::string& w) {
        if (isSingleCjkCodepoint(w) && !isSingleCharStopword(w)) {
            return quoteToken(w) + "*";
        }
        return quoteToken(w);
    };
    auto groupExpr = [&wordExpr](const std::vector<std::string>& g) {
        if (g.size() == 1) return wordExpr(g[0]);
        std::string e = "(";
        for (size_t i = 0; i < g.size(); ++i) {
            if (i > 0) e += " OR ";
            e += wordExpr(g[i]);
        }
        e += ")";
        return e;
    };

    if (groups.size() == 1) {
        const std::vector<std::string>& g = groups.begin()->second;
        if (g.size() == 1) {
            // 单字 CJK 非停用词走前缀；其余（多字词、ASCII、停用词）与原来一字不差。
            if (g[0] == token) {
                return wordExpr(token);
            }
            return quoteToken(token);  // 与原来一字不差
        }
        return groupExpr(g);
    }

    std::string out;
    for (const auto& kv : groups) {
        if (!out.empty()) out += joiner;
        out += groupExpr(kv.second);
    }
    for (const std::string& w : unclaimed) {
        if (!out.empty()) out += joiner;
        // 同义词展开（B3-r2）：未被认领的词同样查表，命中则与 expansions 组成 OR 组。
        const SynonymEntry* e = findSynonyms(w.c_str());
        if (e == nullptr) {
            out += wordExpr(w);
            continue;
        }
        std::string expr = "(" + wordExpr(w);
        for (int k = 0; k < e->expansionCount; ++k) {
            expr += " OR " + wordExpr(e->expansions[k]);
        }
        expr += ")";
        out += expr;
    }
    return out;
}

// AND 连接版（原 expandTokenOrQuery 行为，一字不差）。
std::string expandTokenOrQuery(const std::string& token) {
    return expandTokenWithJoiner(token, " AND ");
}

// 单 token 查询的 OR 放宽版（GAP-TOK-001）：组间 OR 连接，召回更宽。
std::string expandTokenOrSingle(const std::string& token) {
    return expandTokenWithJoiner(token, " OR ");
}

// 第二击：单 token DF-zero 子词的单字前缀分解召回（P1 v09-t005-q01 修复）。
// 仅当调用方确认"第一击 substringRecallPass 过滤全空"时调用。
// 逻辑：
//  1. CutForSearch(token) 取词、去重保序；
//  2. 对每个词 w，若"多字、含非 ASCII 字节、quoteToken(w) 的 DF 为 0"，则记为待分解词；
//     若无待分解词，直接返回 false（不打扰原 fail-open，一次多余查询都不做）；
//  3. 构造分解查询：base = expandTokenWithJoiner(token, " OR ")，
//     对每个待分解词 w，在 base 中把 quoteToken(w) 的每一次出现替换为单字组
//     （单字组构造：按 UTF-8 码点遍历 w，跳过 isSingleCharStopword(cp) 的字；
//      单个 CJK 非停用字用 quoteToken(cp)+"*" 前缀，其余用 quoteToken(cp)；
//      组内以 " OR " 连接并用括号包裹；若组空则跳过该词、不替换）；
//  4. db.searchFts(分解查询, limit*2) 取候选；
//  5. 精滤：hay（title + '\n' + content/snippet）必须包含 token 的全部非停用字
//     （按 UTF-8 码点拆 token，跳过 isSingleCharStopword 的字；用 containsFolded 判断，
//      ASCII 大小写不敏感）；
//  6. 过滤后非空 → hits = filtered，返回 true；为空 → 返回 false（调用方保留原结果）。
// 触发面：仅单 token 且第一击精滤全空且存在 DF-zero 多字词时才真正发查询；
// 前向声明（定义在后）。
bool containsFolded(const std::string& haystack, const std::string& needle);

static bool tryCharDecomposedSingle(const std::string& token, Database& db,
                                    int limit, std::vector<Hit>& hits) {
    std::vector<std::string> words;
    const cppjieba::Jieba* jieba = jiebaInstance();
    if (jieba != nullptr) {
        try {
            jieba->CutForSearch(token, words);
        } catch (...) {
            words.clear();
        }
    }
    std::vector<std::string> uniqWords;
    for (const std::string& w : words) {
        if (w.empty()) continue;
        if (std::find(uniqWords.begin(), uniqWords.end(), w) == uniqWords.end()) {
            uniqWords.push_back(w);
        }
    }
    std::vector<std::string> decompose;
    for (const std::string& w : uniqWords) {
        if (isSingleCjkCodepoint(w)) continue;
        bool hasNonAscii = false;
        for (unsigned char c : w) {
            if (c >= 0x80) { hasNonAscii = true; break; }
        }
        if (!hasNonAscii) continue;
        if (!db.searchFts(quoteToken(w), 1).empty()) continue;
        decompose.push_back(w);
    }
    if (decompose.empty()) return false;

    std::string base = expandTokenWithJoiner(token, " OR ");
    for (const std::string& w : decompose) {
        std::string grp = "(";
        bool firstC = true, anyC = false;
        for (size_t i = 0; i < w.size();) {
            unsigned char c = static_cast<unsigned char>(w[i]);
            size_t len = 1;
            if (c >= 0xF0) len = 4;
            else if (c >= 0xE0) len = 3;
            else if (c >= 0xC0) len = 2;
            if (i + len > w.size()) len = w.size() - i;
            std::string cp = w.substr(i, len);
            i += len;
            if (isSingleCharStopword(cp)) continue;
            if (!firstC) grp += " OR ";
            if (isSingleCjkCodepoint(cp) && !isSingleCharStopword(cp)) {
                grp += quoteToken(cp) + "*";
            } else {
                grp += quoteToken(cp);
            }
            firstC = false;
            anyC = true;
        }
        if (!anyC) continue;
        grp += ")";
        const std::string needle = quoteToken(w);
        std::string replaced;
        replaced.reserve(base.size());
        size_t pos = 0;
        while (true) {
            size_t hit = base.find(needle, pos);
            if (hit == std::string::npos) {
                replaced.append(base, pos, std::string::npos);
                break;
            }
            replaced.append(base, pos, hit - pos);
            replaced += grp;
            pos = hit + needle.size();
        }
        base = std::move(replaced);
    }

    std::vector<Hit> cand = db.searchFts(base, limit * 2);
    std::vector<std::string> needCps;
    for (size_t i = 0; i < token.size();) {
        unsigned char c = static_cast<unsigned char>(token[i]);
        size_t len = 1;
        if (c >= 0xF0) len = 4;
        else if (c >= 0xE0) len = 3;
        else if (c >= 0xC0) len = 2;
        if (i + len > token.size()) len = token.size() - i;
        std::string cp = token.substr(i, len);
        i += len;
        if (isSingleCharStopword(cp)) continue;
        needCps.push_back(cp);
    }
    std::vector<Hit> filtered;
    filtered.reserve(cand.size());
    for (const Hit& h : cand) {
        std::string hay = h.title;
        if (auto content = db.getContentById(h.doc_id)) {
            hay.push_back('\n');
            hay += *content;
        } else {
            hay += h.snippet;
        }
        bool ok = true;
        for (const std::string& cp : needCps) {
            if (!containsFolded(hay, cp)) { ok = false; break; }
        }
        if (ok) filtered.push_back(h);
    }
    if (filtered.empty()) return false;
    hits = std::move(filtered);
    return true;
}

// D4（DF-zero 丢弃）辅助：对每个 token 探测其"展开后表达式"的 DF，

// D4（DF-zero 丢弃）辅助：对每个 token 探测其"展开后表达式"的 DF，
// 为空则视为对 AND 查询零贡献。关键：探测 expandTokenOrQuery(t) 的输出，
// 而不是裸 token —— 该输出内部已含 D3 单字 CJK 前缀（"进"→`"进"*`）与
// 同义词 OR 组，因此 D3 兼容是构造性成立的（裸 token DF=0 不代表展开式 DF=0）。
// static 限定本 TU 可见；仅在 AND 为空时被调用，每 token 一次 LIMIT 1 探测。
static std::vector<std::string> dropZeroDfTokens(const std::vector<std::string>& tokens,
                                                Database& db) {
    std::vector<std::string> kept;
    kept.reserve(tokens.size());
    for (const auto& t : tokens) {
        if (t.empty()) continue;
        const std::string expanded = expandTokenOrQuery(t);
        if (expanded.empty()) continue;  // 展开为空视作零贡献，丢弃
        if (!db.searchFts(expanded, 1).empty()) {
            kept.push_back(t);
        }
    }
    return kept;
}

// D4 stage 1.5 共用：AND 为空时尝试 DF-pruned AND；
// 成功则返回 true 且 hits 被替换，失败返回 false（调用方继续原级联）。
static bool tryDfPrunedAnd(const std::vector<std::string>& tokens, Database& db,
                           int limit, std::vector<Hit>& hits) {
    std::vector<std::string> kept = dropZeroDfTokens(tokens, db);
    if (kept.empty() || kept.size() >= tokens.size()) return false;  // fail-open
    std::string joined;
    for (size_t i = 0; i < kept.size(); ++i) {
        if (i) joined += ' ';
        joined += kept[i];
    }
    std::vector<Hit> refill = db.searchFts(Searcher::buildMatchQuery(joined), limit * 2);
    if (refill.empty()) return false;
    hits = std::move(refill);
    return true;
}

std::string Searcher::buildMatchQuery(const std::string& query) {
    const std::vector<std::string> tokens = splitTokens(query);
    std::string out;
    for (size_t i = 0; i < tokens.size(); ++i) {
        if (i > 0) {
            // 注意：不能用空格隐式 AND——展开后的括号 OR 组与引号串相邻时，
            // FTS5 会报 syntax error，必须显式 AND。
            out += " AND ";
        }
        out += expandTokenOrQuery(tokens[i]);
    }
    return out;
}

std::string Searcher::buildOrMatchQuery(const std::string& query) {
    const std::vector<std::string> tokens = splitTokens(query);
    std::string out;
    for (size_t i = 0; i < tokens.size(); ++i) {
        if (i > 0) {
            out += " OR ";
        }
        out += expandTokenOrQuery(tokens[i]);
    }
    return out;
}

// 把 token 列表展开为子串召回用的 OR 查询：中文 token 按 UTF-8 码点拆成单字
// （跳过单字停用词），ASCII token 保持原样。返回如 `"猫" OR "砂"`，无可用
// 部分时返回空字符串。
std::string buildSubstringRecallQuery(const std::vector<std::string>& tokens) {
    std::vector<std::string> parts;
    for (const std::string& t : tokens) {
        bool hasNonAscii = false;
        for (unsigned char c : t) {
            if (c >= 0x80) { hasNonAscii = true; break; }
        }
        if (!hasNonAscii) {
            if (!t.empty()) parts.push_back(quoteToken(t));
            continue;
        }
        for (size_t i = 0; i < t.size();) {
            unsigned char c = static_cast<unsigned char>(t[i]);
            size_t len = 1;
            if (c >= 0xF0) len = 4;
            else if (c >= 0xE0) len = 3;
            else if (c >= 0xC0) len = 2;
            if (i + len > t.size()) len = t.size() - i;
            std::string cp = t.substr(i, len);
            if (!isSingleCharStopword(cp)) parts.push_back(quoteToken(cp));
            i += len;
        }
    }
    // 去重保序。
    std::vector<std::string> uniq;
    for (const std::string& p : parts) {
        if (std::find(uniq.begin(), uniq.end(), p) == uniq.end()) uniq.push_back(p);
    }
    std::string out;
    for (size_t i = 0; i < uniq.size(); ++i) {
        if (i > 0) out += " OR ";
        out += uniq[i];
    }
    return out;
}

// ASCII 大小写不敏感的子串判断（索引侧 emitToken 对 ASCII 做了小写折叠，
// 因此比较前把双方的 ASCII 大写折成小写；CJK 按字节精确匹配）。
bool containsFolded(const std::string& haystack, const std::string& needle) {
    if (needle.empty()) return true;
    std::string h = haystack, n = needle;
    for (char& c : h) {
        unsigned char uc = static_cast<unsigned char>(c);
        if (uc >= 'A' && uc <= 'Z') c = static_cast<char>(uc - 'A' + 'a');
    }
    for (char& c : n) {
        unsigned char uc = static_cast<unsigned char>(c);
        if (uc >= 'A' && uc <= 'Z') c = static_cast<char>(uc - 'A' + 'a');
    }
    return h.find(n) != std::string::npos;
}

// 子串召回精验（Fix B）：对每个查询 token 按 CutForSearch 切词，要求
// hay（标题+正文原文）包含切出的每一个非空词（ASCII 大小写折叠）。
// 旧逻辑要求"原文连续包含整串 token"，在查询/索引分词粒度不对齐时漏召回
// （如查询"戚风塌腰"成词、文档中"总塌腰"被索引成"塌"/"腰"）。
// 只在 search()/searchQuestion() 的 hits.empty() 分支调用。
bool substringRecallPass(const std::string& hay, const std::vector<std::string>& tokens) {
    const cppjieba::Jieba* jieba = jiebaInstance();
    for (const std::string& t : tokens) {
        std::vector<std::string> words;
        if (jieba != nullptr) {
            try {
                jieba->CutForSearch(t, words);
            } catch (...) {
                words.clear();
            }
        }
        if (words.empty()) {
            words.push_back(t);  // 切词不可用时退化为整串（旧行为）
        }
        for (const std::string& w : words) {
            if (w.empty()) continue;
            if (!containsFolded(hay, w)) return false;
        }
    }
    return true;
}

// 短语后过滤：只保留 title+原文（取不到原文则用 snippet）按 containsFolded
// 连续包含每个短语的 hit。phrases 为空时原样返回。
std::vector<Hit> filterByPhrases(std::vector<Hit> hits, Database& db,
                                 const std::vector<std::string>& phrases) {
    if (phrases.empty()) {
        return hits;
    }
    std::vector<Hit> out;
    out.reserve(hits.size());
    for (auto& h : hits) {
        std::string body;
        if (auto content = db.getContentById(h.doc_id)) {
            body = *content;
        } else {
            body = h.snippet;
        }
        const std::string haystack = h.title + "\n" + body;
        bool ok = true;
        for (const auto& p : phrases) {
            if (!containsFolded(haystack, p)) {
                ok = false;
                break;
            }
        }
        if (ok) {
            out.push_back(std::move(h));
        }
    }
    return out;
}

// 去除首尾 ASCII 空白字符。
static std::string trimStr(const std::string& s) {
    size_t b = 0;
    size_t e = s.size();
    while (b < e && (s[b] == ' ' || s[b] == '\t' || s[b] == '\r' || s[b] == '\n' ||
                     s[b] == '\f' || s[b] == '\v')) {
        ++b;
    }
    while (e > b && (s[e - 1] == ' ' || s[e - 1] == '\t' || s[e - 1] == '\r' ||
                     s[e - 1] == '\n' || s[e - 1] == '\f' || s[e - 1] == '\v')) {
        --e;
    }
    return s.substr(b, e - b);
}

// 删除所有 <...> 片段。
static std::string stripHtmlTags(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    size_t i = 0;
    while (i < s.size()) {
        if (s[i] == '<') {
            size_t j = s.find('>', i + 1);
            if (j == std::string::npos) {
                break;
            }
            i = j + 1;
        } else {
            out.push_back(s[i]);
            ++i;
        }
    }
    return out;
}

// 抽取标题行文本：
//  - HTML: <h1>..</h6> 标签内文本（先 stripHtmlTags）
//  - Markdown: 行首 1-6 个 '#' 加空格开头的行（去掉行首 # 和空格）
// 结果行内首尾空白均 trim。
static std::vector<std::string> extractHeadingTexts(const std::string& content) {
    std::vector<std::string> out;
    // HTML 标题：扫描 <h1>..</h6>（大小写不敏感的首字符判断，简单匹配 'h'/'H' + '1'..'6'）。
    for (size_t i = 0; i < content.size(); ++i) {
        if (content[i] != '<') {
            continue;
        }
        if (i + 2 >= content.size()) {
            continue;
        }
        char c1 = content[i + 1];
        if (c1 != 'h' && c1 != 'H') {
            continue;
        }
        char c2 = content[i + 2];
        if (c2 < '1' || c2 > '6') {
            continue;
        }
        size_t after = i + 3;
        if (after >= content.size()) {
            continue;
        }
        if (content[after] != '>') {
            continue;
        }
        size_t textStart = after + 1;
        // 找结束标签 </hN>
        std::string closeTag = "</";
        closeTag.push_back(c1);
        closeTag.push_back(c2);
        closeTag.push_back('>');
        size_t closePos = content.find(closeTag, textStart);
        if (closePos == std::string::npos) {
            continue;
        }
        std::string inner = content.substr(textStart, closePos - textStart);
        std::string text = trimStr(stripHtmlTags(inner));
        if (!text.empty()) {
            out.push_back(text);
        }
        i = closePos + closeTag.size() - 1;
    }
    // Markdown 标题：按行扫描。
    size_t pos = 0;
    while (pos <= content.size()) {
        size_t nl = content.find('\n', pos);
        std::string line = (nl == std::string::npos)
                               ? content.substr(pos)
                               : content.substr(pos, nl - pos);
        // 去掉行尾 \r
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        size_t hashes = 0;
        while (hashes < line.size() && hashes < 6 && line[hashes] == '#') {
            ++hashes;
        }
        if (hashes >= 1 && hashes <= 6 && hashes < line.size() && line[hashes] == ' ') {
            std::string text = trimStr(line.substr(hashes + 1));
            if (!text.empty()) {
                out.push_back(text);
            }
        }
        if (nl == std::string::npos) {
            break;
        }
        pos = nl + 1;
    }
    return out;
}

// 抽取列表项文本：
//  - HTML: <li>..</li> 内文本（先 stripHtmlTags）
//  - Markdown: "- "/"* " 行去掉标记；"数字. " 行去掉标记
// 结果行内首尾空白均 trim。
// 去掉单行的 Markdown 列表标记：行首 "- "/"* " 去 2 字符；行首 "数字. " 去标记部分。
// 不处理 '#'（标题行由调用方 R3'/R6' 提前跳过）。
static std::string stripListMarker(const std::string& line) {
    if (line.size() >= 2 && (line[0] == '-' || line[0] == '*') && line[1] == ' ') {
        return line.substr(2);
    }
    size_t d = 0;
    while (d < line.size() && line[d] >= '0' && line[d] <= '9') {
        ++d;
    }
    if (d >= 1 && d + 1 < line.size() && line[d] == '.' && line[d + 1] == ' ') {
        return line.substr(d + 2);
    }
    return line;
}

// UTF-8 码点长度判断（返回该首字节对应的序列字节数，1-4；非法返回 1）。
static size_t utf8CharLen(unsigned char c) {
    if ((c & 0x80) == 0x00) return 1;
    if ((c & 0xE0) == 0xC0) return 2;
    if ((c & 0xF0) == 0xE0) return 3;
    if ((c & 0xF8) == 0xF0) return 4;
    return 1;
}

// 按 UTF-8 码点切分字符串。
static std::vector<std::string> splitUtf8Codepoints(const std::string& s) {
    std::vector<std::string> out;
    size_t i = 0;
    while (i < s.size()) {
        size_t len = utf8CharLen(static_cast<unsigned char>(s[i]));
        if (i + len > s.size()) {
            len = 1;
        }
        out.push_back(s.substr(i, len));
        i += len;
    }
    return out;
}

// 统计子串出现次数（不重叠，使用 std::string::find 循环实现）。
static int countSubstringOccurrences(const std::string& haystack,
                                     const std::string& needle) {
    if (needle.empty()) {
        return 0;
    }
    int count = 0;
    size_t pos = 0;
    while ((pos = haystack.find(needle, pos)) != std::string::npos) {
        ++count;
        pos += needle.size();
    }
    return count;
}

static void scoreOneHit(Hit& hit,
                        const std::vector<std::string>& tokens,
                        const std::string& query,
                        const SearchWeights& weights,
                        const std::vector<std::string>& phrases,
                        Database& db,
                        ScoreBreakdown& bd) {
    bd = ScoreBreakdown{};
    bd.baseBm25 = hit.score;
    double finalScore = hit.score;  // base = -bm25，越大越相关
    const std::string longQuery = removeWhitespace(query);

    // title 加成：每个 query token 在 title 中出现为子串，+1.0。
    for (const std::string& token : tokens) {
        if (hit.title.find(token) != std::string::npos) {
            finalScore += weights.titleBoost;
            bd.titleBonus += weights.titleBoost;
        }

    }

    // 短语加成：去掉空白的连续查询串出现在 title 或 snippet 中，+2.0。
    if (!longQuery.empty()) {
        if (hit.title.find(longQuery) != std::string::npos ||
            hit.snippet.find(longQuery) != std::string::npos) {
            finalScore += weights.phraseBoost;
            bd.phraseBonus += weights.phraseBoost;
        }

    }

    // ===== 新增结构加成规则 R1-R6（全部在 phraseBoost 块之后执行） =====
    // 前置：判断 title 是否退化为文件名 stem。
    bool titleDegraded = false;
    if (hit.title.empty()) {
        titleDegraded = true;
    } else {
        std::string stem = hit.path;
        size_t slash = stem.find_last_of('/');
        if (slash != std::string::npos) {
            stem = stem.substr(slash + 1);
        }
        size_t dot = stem.find_last_of('.');
        if (dot != std::string::npos) {
            stem = stem.substr(0, dot);
        }
        if (hit.title == stem) {
            titleDegraded = true;
        }
    }

    // 取 content；取不到则跳过 R1-R6 全部规则。
    std::string content;
    bool hasContent = false;
    if (auto c = db.getContentById(hit.doc_id)) {
        content = *c;
        hasContent = true;
    }

    if (hasContent) {
        // R7（单 token 时间单位序数结构加成）
        if (tokens.size() == 1) {
            const std::string& tok = tokens[0];
            std::string unit;
            // 后缀匹配单位表：双字优先
            const char* kU2[] = {"季度", "小时", "分钟"};
            const char* kU1[] = {"月", "周", "天", "年"};
            for (const char* u : kU2) {
                std::string su(u);
                if (tok.size() >= su.size() && tok.compare(tok.size() - su.size(), su.size(), su) == 0) { unit = su; break; }
            }
            if (unit.empty()) {
                for (const char* u : kU1) {
                    std::string su(u);
                    if (tok.size() >= su.size() && tok.compare(tok.size() - su.size(), su.size(), su) == 0) { unit = su; break; }
                }
            }
            if (!unit.empty() && (hit.title.find(tok) != std::string::npos || titleDegraded)) {
                const char* kNum[] = {"一", "二", "三", "四", "五", "六", "七", "八", "九", "十"};
                int distinct = 0;
                int total = 0;
                for (const char* n : kNum) {
                    // 形态一：“第”+数字+“个”+单位（如“第一个月”）
                    std::string patWithGe = std::string("第") + n + "个" + unit;
                    int cntWithGe = countSubstringOccurrences(content, patWithGe);
                    // 形态二：“第”+数字+单位（如“第一周”）
                    std::string patPlain = std::string("第") + n + unit;
                    int cntPlain = countSubstringOccurrences(content, patPlain);
                    int cnt = cntWithGe + cntPlain;
                    if (cnt > 0) ++distinct;
                    total += cnt;
                }
                if (distinct >= 2) {
                    // distinct 奖励“按序数分节的结构化”，total 奖励“覆盖深度”
                    finalScore += static_cast<double>(distinct) * 1.0 + static_cast<double>(total) * 0.5;
                    bd.structuralBonus += static_cast<double>(distinct) * 1.0 + static_cast<double>(total) * 0.5;
                }
            }
        }
        // R1（标题行 token 加成）：仅 titleDegraded 为真时。按 token 计：标题行
        // stripHtmlTags 去首尾空白后，以该 token 开头则计 1.5（行首=包含的强化形式），
        // 否则含该 token 子串则计 weights.titleBoost；二者取其一，不叠加。
        // 每文档封顶 +2.0。R5 已并入此处，不再作为独立加成叠加。
        if (titleDegraded) {
    std::vector<std::string> headings = extractHeadingTexts(content);
    double r1Gain = 0.0;
    for (const auto& tok : tokens) {
        if (tok.empty()) {
            continue;
        }
        bool startsWith = false;
        bool contains = false;
        for (const auto& h : headings) {
            std::string t = trimStr(stripHtmlTags(h));
            if (t.size() >= tok.size() &&
                t.compare(0, tok.size(), tok) == 0) {
                startsWith = true;
                break;
            }
            if (t.find(tok) != std::string::npos) {
                contains = true;
            }
        }
        if (startsWith) {
            r1Gain += 1.5;
        } else if (contains) {
            // R1 收紧：仅“包含”不再给满 titleBoost，降为 0.25，
            // 避免通用词（如“拉伸”）把非目标文档抬进 top10 后反超。
            r1Gain += 0.25;
        }
    }
    if (r1Gain > 2.0) {
        r1Gain = 2.0;
    }
    finalScore += r1Gain;
    bd.structuralBonus += r1Gain;
        }

        // R2（块级同现）：仅 tokens.size()>=2 时。跳过含 "<title" 的行，跳过
        // stripHtmlTags 后与 hit.title 完全相同的行。某一行同时含全部 token 子串则 +0.5，
        // 每文档封顶 +1.0（至多两行起效）。
        if (tokens.size() >= 2) {
            double r2Gain = 0.0;
            size_t linePos = 0;
            while (linePos <= content.size()) {
                size_t nl = content.find('\n', linePos);
                std::string line = (nl == std::string::npos)
                                       ? content.substr(linePos)
                                       : content.substr(linePos, nl - linePos);
                if (!line.empty() && line.back() == '\r') {
                    line.pop_back();
                }
                bool skip = false;
                if (line.find("<title") != std::string::npos) {
                    skip = true;
                }
                if (!skip) {
                    if (stripHtmlTags(line) == hit.title) {
                        skip = true;
                    }
                }
                if (!skip) {
                    bool allPresent = true;
                    for (const auto& tok : tokens) {
                        if (tok.empty() || line.find(tok) == std::string::npos) {
                            allPresent = false;
                            break;
                        }
                    }
                    if (allPresent) {
                        r2Gain += 0.5;
                        if (r2Gain >= 1.0) {
                            r2Gain = 1.0;
                            break;
                        }
                    }
                }
                if (nl == std::string::npos) {
                    break;
                }
                linePos = nl + 1;
            }
            finalScore += r2Gain;
            bd.structuralBonus += r2Gain;
        }

        // R2b（首段兑现）：仅 tokens.size()>=2 时。若 hit.title 含全部 token，且 content
        // 第一个"有效行"同时含全部 token，则 finalScore += 0.5（每文档一次）。
        // "有效行"定义：按 '\n' 切行，跳过含 "<title" 的行、跳过 stripHtmlTags+trimStr 后
        // 与 hit.title 完全相同的行、跳过 stripHtmlTags+trimStr 后为空的行；第一个不跳过的
        // 行即首个有效行。token 命中判断用去标签 trim 后的行文本。
        // IR 依据：标题承诺了查询、开篇第一段就兑现，是强相关信号；标题缺 token 时不触发，
        // 避免给"引言顺带提到"的文档加分。
        if (tokens.size() >= 2) {
            bool titleHasAll = true;
            for (const auto& tok : tokens) {
                if (tok.empty() || hit.title.find(tok) == std::string::npos) {
                    titleHasAll = false;
                    break;
                }
            }
            if (titleHasAll) {
                std::string firstValid;
                bool foundValid = false;
                std::size_t lineStart = 0;
                while (lineStart <= content.size()) {
                    std::size_t lineEnd = content.find('\n', lineStart);
                    std::string line = (lineEnd == std::string::npos)
                        ? content.substr(lineStart)
                        : content.substr(lineStart, lineEnd - lineStart);
                    if (line.find("<title") != std::string::npos) {
                        // 跳过 <title 行
                    } else {
                        std::string t = trimStr(stripHtmlTags(line));
                        if (t.empty() || t == hit.title) {
                            // 跳过空行或与 hit.title 完全相同的行
                        } else {
                            firstValid = t;
                            foundValid = true;
                            break;
                        }
                    }
                    if (lineEnd == std::string::npos) {
                        break;
                    }
                    lineStart = lineEnd + 1;
                }
                if (foundValid) {
                    bool lineHasAll = true;
                    for (const auto& tok : tokens) {
                        if (tok.empty() || firstValid.find(tok) == std::string::npos) {
                            lineHasAll = false;
                            break;
                        }
                    }
                    if (lineHasAll) {
                        finalScore += 0.5;
                        bd.structuralBonus += 0.5;
                    }
                }
            }
        }

        // R3'（行首命中）：把 content 按行切分，对每行去标签、去列表标记后，若以 longQuery
        // 开头则 +1.0（每文档只加一次）。
        // 行首命中是文档把查询词当作条目/段首的强信号；跳过 # 标题行避免与 R1 重复计算。
        if (!longQuery.empty()) {
            size_t pos = 0;
            while (pos <= content.size()) {
                size_t nl = content.find('\n', pos);
                std::string line = (nl == std::string::npos)
                                       ? content.substr(pos)
                                       : content.substr(pos, nl - pos);
                if (!line.empty() && line.back() == '\r') {
                    line.pop_back();
                }
                std::string t = trimStr(stripHtmlTags(line));
                if (!t.empty() && t[0] == '#') {
                    if (nl == std::string::npos) {
                        break;
                    }
                    pos = nl + 1;
                    continue;
                }
                std::string t2 = trimStr(stripListMarker(t));
                if (t2.size() >= longQuery.size() &&
                    t2.compare(0, longQuery.size(), longQuery) == 0) {
                    finalScore += 1.0;
                    bd.structuralBonus += 1.0;
                    break;
                }
                if (nl == std::string::npos) {
                    break;
                }
                pos = nl + 1;
            }
        }

        // R4（主题前缀）：仅 titleDegraded 为真时。对每个 token：若其在 content 中出现 >=1 次则跳过；
        // 否则枚举其真前缀（UTF-8 码点长度 >=3），若任一前缀在 content 中出现 >=3 次则 +0.5
        //（每文档只加一次）。
        if (titleDegraded) {
            for (const auto& tok : tokens) {
                if (tok.empty()) {
                    continue;
                }
                if (countSubstringOccurrences(content, tok) >= 1) {
                    continue;
                }
                std::vector<std::string> cps = splitUtf8Codepoints(tok);
                if (cps.size() < 3) {
                    continue;
                }
                bool added = false;
                std::string prefix;
                for (size_t k = 0; k + 1 < cps.size(); ++k) {
                    prefix += cps[k];
                    size_t cpLen = k + 1;
                    if (cpLen >= 3) {
                        if (countSubstringOccurrences(content, prefix) >= 3) {
                            finalScore += 0.5;
                            bd.structuralBonus += 0.5;
                            added = true;
                            break;
                        }
                    }
                }
                if (added) {
                    break;
                }
            }
        }



        // R6'（行首命中 + 数字）：在同一按行切分的逻辑下，若某行去标签、去列表标记后以
        // longQuery 开头且含数字（ASCII 0-9 或中文数字字符），则 +2.5（每文档只加一次，
        // 可与 R3' 叠加）。行首命中是文档把查询词当作清单条目的强信号。
        if (!longQuery.empty()) {
            static const std::string cnDigits = "一二三四五六七八九十百千万两";
            size_t pos = 0;
            while (pos <= content.size()) {
                size_t nl = content.find('\n', pos);
                std::string line = (nl == std::string::npos)
                                       ? content.substr(pos)
                                       : content.substr(pos, nl - pos);
                if (!line.empty() && line.back() == '\r') {
                    line.pop_back();
                }
                std::string t = trimStr(stripHtmlTags(line));
                if (!t.empty() && t[0] == '#') {
                    if (nl == std::string::npos) {
                        break;
                    }
                    pos = nl + 1;
                    continue;
                }
                std::string t2 = trimStr(stripListMarker(t));
                if (t2.size() < longQuery.size() ||
                    t2.compare(0, longQuery.size(), longQuery) != 0) {
                    if (nl == std::string::npos) {
                        break;
                    }
                    pos = nl + 1;
                    continue;
                }
                bool hasDigit = false;
                for (char ch : t2) {
                    if (ch >= '0' && ch <= '9') {
                        hasDigit = true;
                        break;
                    }
                }
                if (!hasDigit) {
                    for (size_t ci = 0; ci < cnDigits.size();) {
                        size_t clen = utf8CharLen(static_cast<unsigned char>(cnDigits[ci]));
                        std::string cp = cnDigits.substr(ci, clen);
                        if (t2.find(cp) != std::string::npos) {
                            hasDigit = true;
                            break;
                        }
                        ci += clen;
                    }
                }
                if (hasDigit) {
                    finalScore += 2.5;
                    bd.structuralBonus += 2.5;
                    break;
                }
                if (nl == std::string::npos) {
                    break;
                }
                pos = nl + 1;
            }
        }
    }
    // ===== 新增结构加成规则结束 =====

    hit.score = finalScore;
    bd.finalScore = finalScore;
}

static void applyQuotedPhraseBonus(Hit& hit,
                                   const std::vector<std::string>& phrases,
                                   const SearchWeights& weights,
                                   ScoreBreakdown& bd) {
    const std::string haystack = hit.title + "\n" + hit.snippet;
    for (const auto& p : phrases) {
        if (containsFolded(haystack, p)) {
            hit.score += weights.phraseBoost;
            bd.phraseBonus += weights.phraseBoost;
        }
    }
}

struct ScoredHit { Hit hit; ScoreBreakdown breakdown; };

static std::vector<ScoredHit> rerankScored(std::vector<Hit> hits,
                                           const std::vector<std::string>& tokens,
                                           const std::string& query,
                                           const SearchWeights& weights,
                                           int limit,
                                           const std::vector<std::string>& phrases,
                                           Database& db) {
    if (hits.empty()) {
        return {};
    }

    std::vector<ScoredHit> scored;
    scored.reserve(hits.size());
    for (Hit& hit : hits) {
        ScoreBreakdown bd;
        scoreOneHit(hit, tokens, query, weights, phrases, db, bd);
        scored.push_back(ScoredHit{std::move(hit), bd});
    }

    // 短语加成：title 或 snippet 连续包含短语，+phraseBoost。
    // 注意：必须在排序与截断之前执行（与原 rerankHits 顺序一致），否则加成影响不了排序。
    for (auto& s : scored) {
        applyQuotedPhraseBonus(s.hit, phrases, weights, s.breakdown);
    }

    // 按总分降序排序。
    std::stable_sort(scored.begin(), scored.end(),
                     [](const ScoredHit& a, const ScoredHit& b) { return a.hit.score > b.hit.score; });

    // 截断到 limit。
    if (static_cast<int>(scored.size()) > limit) {
        scored.resize(static_cast<size_t>(limit));
    }

    return scored;
}

static std::vector<Hit> rerankHits(std::vector<Hit> hits,
                            const std::vector<std::string>& tokens,
                            const std::string& query,
                            const SearchWeights& weights,
                            int limit,
                            const std::vector<std::string>& phrases,
                            Database& db) {
    std::vector<ScoredHit> scored = rerankScored(std::move(hits), tokens, query, weights, limit, phrases, db);
    std::vector<Hit> out;
    out.reserve(scored.size());
    for (auto& s : scored) {
        out.push_back(std::move(s.hit));
    }
    return out;
}

// t019-q12 改动点 3 保守版：相邻 token 前缀/子串交叉探测。
//
// 背景：查询侧切词（parseNaturalQuery/jieba CutForSearch）与索引侧切词在
// 连续中文片段上可能错位，例如"长期不弹琴"查询侧切为 [长期][不][弹琴]，
// 而文档侧切为 [长期][不弹]。此时 AND 必空、D4 的 DF 探测（逐 token 展开）
// 认不出"错位"、OR 召回被高频 token 稀释排序、子串回退不触发。
//
// 本函数只在 hits.empty() 时被调用。对 tokens 的每个相邻对 (a, b) 生成
// 候选集合 {a+b, a+b首字, a首字+b}（"首字"指首个 UTF-8 码点），逐个用
// db_.searchFts(quoteToken(cand), 1) 探测；任一候选命中即停（保守，避免
// 组合爆炸）。命中后把 quoteToken(cand) 作为高权重项并入 OR 查询重查，
// 结果写入 hits 并直接返回，由上层 rerankHits 排序。
//
// 复用设施：quoteToken、Database::searchFts、splitUtf8Codepoints；
// orQuery 由调用点（Searcher::search 成员函数内）经 buildOrMatchQuery(rest) 算好传入。
static void tryAdjacentPrefixProbe(const std::vector<std::string>& tokens,
                                   const std::string& orQuery,
                                   Database& db,
                                   int limit,
                                   std::vector<Hit>& hits) {
    // 注意：tokens 是空白切分的粗块（如"长期不弹琴"整块），不是 jieba 细 token。
    // 相邻探测必须在 jieba token 粒度上做：先把每个粗块用 CutForSearch 展开为
    // 细 token 序列，再做相邻对候选生成。否则 a+b 候选（如"长期不弹琴琴弦"）
    // 永远拼不出索引侧的真实连续片段（如"不弹"）。
    std::vector<std::string> jtoks;
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba != nullptr) {
        for (const std::string& t : tokens) {
            std::vector<std::string> words;
            try {
                jieba->CutForSearch(t, words);
            } catch (...) {
                words.clear();
            }
            for (const std::string& w : words) {
                if (!w.empty()) {
                    jtoks.push_back(w);
                }
            }
        }
    } else {
        jtoks = tokens;
    }
    if (jtoks.size() < 2) {
        return;
    }
    for (size_t i = 0; i + 1 < jtoks.size(); ++i) {
        const std::string& a = jtoks[i];
        const std::string& b = jtoks[i + 1];

        // UTF-8 首字提取：复用源码已有的 splitUtf8Codepoints。
        std::vector<std::string> aCps = splitUtf8Codepoints(a);
        std::vector<std::string> bCps = splitUtf8Codepoints(b);
        const std::string aHead = aCps.empty() ? std::string() : aCps.front();
        const std::string bHead = bCps.empty() ? std::string() : bCps.front();

        // 候选集合（顺序即探测优先级）：
        //   1) a + b      —— 相邻重组（如"不"+"弹琴"→"不弹琴"）
        //   2) a + b首字  —— 关键候选（如"不"+"弹"→"不弹"，命中索引侧"不弹"）
        //   3) a首字 + b  —— a 被过度切分时回补
        std::vector<std::string> cands;
        cands.push_back(a + b);
        if (!bHead.empty()) {
            cands.push_back(a + bHead);
        }
        if (!aHead.empty()) {
            cands.push_back(aHead + b);
        }

        std::string hitCand;
        for (const std::string& cand : cands) {
            if (cand.empty()) {
                continue;
            }
            std::vector<Hit> probe = db.searchFts(quoteToken(cand), 1);
            if (!probe.empty()) {
                hitCand = cand;
                break;  // 保守：任一候选命中即停
            }
        }
        if (hitCand.empty()) {
            continue;
        }

        // 命中后重查：quoteToken(cand) OR <原 orQuery>。
        std::string reQuery = quoteToken(hitCand);
        if (!orQuery.empty()) {
            reQuery += " OR ";
            reQuery += orQuery;
        }
        std::vector<Hit> requery = db.searchFts(reQuery, limit * 2);
        if (!requery.empty()) {
            hits = std::move(requery);
            return;  // 命中即返回，交由上层 filterByPhrases/rerankHits 收尾
        }
    }
}

static std::vector<Hit> finishScored(std::vector<ScoredHit> scored, std::vector<ScoreBreakdown>* breakdowns) {
    if (breakdowns) {
        breakdowns->clear();
        breakdowns->reserve(scored.size());
        for (const auto& s : scored) breakdowns->push_back(s.breakdown);
    }
    std::vector<Hit> out;
    out.reserve(scored.size());
    for (auto& s : scored) out.push_back(std::move(s.hit));
    return out;
}

std::vector<Hit> Searcher::searchDetailed(const std::string& query, int limit, std::vector<ScoreBreakdown>* breakdowns) {
    if (query.empty() || limit <= 0) {
        return {};
    }

    // 防御：超长/纯标点查询直接返回空（历史 hang：TokenizerLong.VeryLongPunctuationQueryReturnsEmpty）。
    // 此类查询在分词与 FTS5 匹配阶段会退化为病态扫描，导致线程长时间占用。
    {
        constexpr std::size_t kMaxQueryChars = 2000;
        std::size_t char_count = 0;
        bool has_non_punct_non_space = false;
        for (unsigned char c : query) {
            if ((c & 0xC0) != 0x80) {
                ++char_count;
            }
            if (std::isspace(c) == 0 && std::ispunct(c) == 0) {
                has_non_punct_non_space = true;
            }
        }
        if (char_count > kMaxQueryChars || !has_non_punct_non_space) {
            return {};
        }
    }

    // 引号短语先剥离：rest 参与分词召回，phrases 走后过滤与加成。
    std::vector<std::string> phrases;
    std::string rest;
    extractPhrases(query, phrases, rest);

    // B-fix1：search 路径对齐 locate 路径的疑问词过滤，剥离"怎么办"等疑问/语气词，
    // 避免其被 AND 进查询；引号短语已先剥离不受影响。
    rest = stripFillerWords(rest);

    // 停用词过滤：单字停用词不参与检索与排序（GAP-STOPWORD-001）。
    // 注意只过滤整个 token 恰为单字停用词的情况，不拆多字 token；
    // "不"字不在停用词表（否定语义保护），不受影响。
    std::vector<std::string> tokens = splitTokens(rest);
    tokens.erase(std::remove_if(tokens.begin(), tokens.end(), isSingleCharStopword),
                 tokens.end());
    // 单 token 全停用词（如"的了在了"）：切词全是单字停用词时也视为纯停用词查询。
    if (tokens.size() == 1 && phrases.empty() && isAllStopwordsToken(tokens[0])) {
        return {};
    }
    if (tokens.empty() && phrases.empty()) {
        // 纯停用词（或空白）查询：直接返回空。
        return {};
    }

    // 纯短语查询：用短语各自展开 OR 召回候选，后过滤留精确包含者。
    if (tokens.empty() && !phrases.empty()) {
        std::string phraseOrQuery;
        for (size_t i = 0; i < phrases.size(); ++i) {
            if (i > 0) {
                phraseOrQuery += " OR ";
            }
            phraseOrQuery += expandTokenOrQuery(phrases[i]);
        }
        std::vector<Hit> phraseHits = db_.searchFts(phraseOrQuery, limit * 2);
        phraseHits = filterByPhrases(std::move(phraseHits), db_, phrases);
        return finishScored(rerankScored(std::move(phraseHits), tokens, query, weights_, limit, phrases, db_), breakdowns);
    }

    // 1. 精确 AND：多取 2 倍做重排。
    const std::string matchQuery = buildMatchQuery(rest);
    std::vector<Hit> hits = db_.searchFts(matchQuery, limit * 2);

    // 1.4 相邻 token 前缀/子串交叉探测（t019-q12 改动点 3 保守版）：
    //     背景见 tryAdjacentPrefixProbe 注释。只在 hits.empty() 时触发；
    //     已有结果的查询行为一字不变。
    //     注意：tokens.size()>=2 的判断在 helper 内部按 jieba 展开后的 jtoks 做；
    //     中文无空格查询的 tokens 常为单个粗块，不能在这里卡掉。
    if (hits.empty() && !tokens.empty()) {
        tryAdjacentPrefixProbe(tokens, buildOrMatchQuery(rest), db_, limit, hits);
    }

    // 1.5 DF-zero 丢弃（D4）：AND 为空时丢弃零贡献 token，用剩余 token 重建 AND
    //     再查一次，避免直接掉进 OR/子串回退（AND 交集精度高于 OR 并集）。
    //     只在 hits.empty() 时触发；已有结果的查询行为一字不变。
    if (hits.empty() && !tokens.empty()) {
        tryDfPrunedAnd(tokens, db_, limit, hits);
    }

    // 1.6 单 token AND 非空时的漏召回补刀（v09-t007-q08 修复）：单 token 查询
    //     的 AND 展开（expandTokenOrQuery）会把"三个月"这类多字词按 CutForSearch
    //     切成单字 AND，只要索引里"三…个…月"分散出现就命中一批无关文档；而真正
    //     连续含"三个月"的期望文档因索引侧 token 粒度不同不进 AND 结果。此时候
    //     选集非空，阶段 2/3 的 empty-only 守卫全部跳过，漏召回无法补救。
    //     这里补一刀：单 token 且 AND 非空时，尝试 tryCharDecomposedSingle 的
    //     分解 + 全字精滤召回，把结果按 doc_id 去重并入 hits，交给 rerankHits
    //     用短语加成排序。多 token 与 AND 为空的路径完全不受影响。
    if (tokens.size() == 1 && !hits.empty()) {
        std::vector<Hit> extra;
        if (tryCharDecomposedSingle(tokens[0], db_, limit, extra)) {
            std::set<int64_t> seen;
            for (const Hit& h : hits) seen.insert(h.doc_id);
            for (const Hit& h : extra) {
                if (seen.insert(h.doc_id).second) {
                    hits.push_back(h);
                }
            }
        }
    }

    // 2. OR 回退：AND 无结果时放宽为 OR；单 token 查询把组间 AND 换成 OR（GAP-TOK-001）。
    if (hits.empty() && !tokens.empty()) {
        const std::string orQuery =
            tokens.size() >= 2 ? buildOrMatchQuery(rest) : expandTokenOrSingle(tokens[0]);
        std::vector<Hit> orHits = db_.searchFts(orQuery, limit * 2);
        if (tokens.size() == 1) {
            // 单 token OR 召回偏宽，用 substringRecallPass 精确过滤：
            // 只保留原文确实包含查询每个切词的文档，避免"超导材料制备"误命中只含"材料"的文档。
            // fail-open：若严格过滤导致零结果（如"戚风塌腰"的"戚风塌"切词 DF=0），
            // 则保留未过滤的 OR 结果，避免误杀。
            std::vector<Hit> filtered;
            filtered.reserve(orHits.size());
            for (const Hit& h : orHits) {
                std::string hay = h.title;
                if (auto content = db_.getContentById(h.doc_id)) {
                    hay.push_back('\n');
                    hay += *content;
                } else {
                    hay += h.snippet;
                }
                if (substringRecallPass(hay, tokens)) filtered.push_back(h);
            }
            // P1 第二击替代 fail-open：第一击精滤全空时，不再保留未过滤的 orHits
            // （那会复活 v07-038"超导材料制备"误命中"材料"文档的回归），
            // 而是尝试 DF-zero 子词单字分解 + 全字精滤的第二击。
            // 第二击仍空则 orHits 为空（严格精度语义）。
            orHits = std::move(filtered);
            if (orHits.empty()) {
                std::vector<Hit> second;
                if (tryCharDecomposedSingle(tokens[0], db_, limit, second)) {
                    orHits = std::move(second);
                }
            }
        }
        hits = std::move(orHits);
    }

    // 3. 子串召回回退（T2 修复）：AND 与 OR 都无结果时，把中文 token 拆成单字
    //    做 OR 粗筛，再用 substringRecallPass 按 CutForSearch 切词逐个包含精验后保留。
    //    jieba 最长匹配受上下文影响，查询词（如"猫砂"）在索引词汇表中不存在，
    //    但其单字（如"猫"）通常在索引里。纯单字 OR 会过度召回（如"量子纠缠"
    //    的"量/子"遍地都是），因此只保留原文（或标题）中按 CutForSearch 切词
    //    逐个包含每个查询 token 的文档。本阶段只在前两阶段都
    //    为空时触发，不影响任何已有查询的结果。
    if (hits.empty()) {
        const std::string subQuery = buildSubstringRecallQuery(tokens);
        if (!subQuery.empty()) {
            std::vector<Hit> subHits = db_.searchFts(subQuery, limit * 2);
            for (const Hit& h : subHits) {
                std::string hay = h.title;
                if (auto content = db_.getContentById(h.doc_id)) {
                    hay.push_back('\n');
                    hay += *content;
                } else {
                    hay += h.snippet;
                }
                if (substringRecallPass(hay, tokens)) hits.push_back(h);
            }
        }
    }

    hits = filterByPhrases(std::move(hits), db_, phrases);
    return finishScored(rerankScored(std::move(hits), tokens, query, weights_, limit, phrases, db_), breakdowns);
}

std::vector<Hit> Searcher::search(const std::string& query, int limit) {
    return searchDetailed(query, limit, nullptr);
}

std::vector<ExplainedHit> Searcher::explain(const std::string& query, int limit) {
    std::vector<ScoreBreakdown> bds;
    std::vector<Hit> hits = searchDetailed(query, limit, &bds);
    std::vector<ExplainedHit> out;
    out.reserve(hits.size());
    for (size_t i = 0; i < hits.size(); ++i) {
        ExplainedHit e;
        e.hit = std::move(hits[i]);
        e.breakdown = bds[i];
        out.push_back(std::move(e));
    }
    return out;
}

std::vector<Hit> Searcher::searchQuestion(const std::string& query, int limit) {
    if (query.empty() || limit <= 0) {
        return {};
    }

    // 引号短语先剥离：rest 参与分词召回，phrases 走后过滤与加成。
    std::vector<std::string> phrases;
    std::string rest;
    extractPhrases(query, phrases, rest);

    // B-fix1：search 路径对齐 locate 路径的疑问词过滤，剥离"怎么办"等疑问/语气词，
    // 避免其被 AND 进查询；引号短语已先剥离不受影响。
    rest = stripFillerWords(rest);

    // 停用词过滤：单字停用词不参与检索与排序（GAP-STOPWORD-001）。
    // 注意只过滤整个 token 恰为单字停用词的情况，不拆多字 token；
    // "不"字不在停用词表（否定语义保护），不受影响。
    std::vector<std::string> tokens = splitTokens(rest);
    tokens.erase(std::remove_if(tokens.begin(), tokens.end(), isSingleCharStopword),
                 tokens.end());
    // 单 token 全停用词（如"的了在了"）：切词全是单字停用词时也视为纯停用词查询。
    if (tokens.size() == 1 && phrases.empty() && isAllStopwordsToken(tokens[0])) {
        return {};
    }
    if (tokens.empty() && phrases.empty()) {
        // 纯停用词（或空白）查询：直接返回空。
        return {};
    }

    // 纯短语查询：用短语各自展开 OR 召回候选，后过滤留精确包含者。
    if (tokens.empty() && !phrases.empty()) {
        std::string phraseOrQuery;
        for (size_t i = 0; i < phrases.size(); ++i) {
            if (i > 0) {
                phraseOrQuery += " OR ";
            }
            phraseOrQuery += expandTokenOrQuery(phrases[i]);
        }
        std::vector<Hit> phraseHits = db_.searchFts(phraseOrQuery, limit * 2);
        phraseHits = filterByPhrases(std::move(phraseHits), db_, phrases);
        return rerankHits(std::move(phraseHits), tokens, query, weights_, limit, phrases, db_);
    }

    // 1. 精确 AND：多取 2 倍做重排。
    const std::string matchQuery = buildMatchQuery(rest);
    std::vector<Hit> hits = db_.searchFts(matchQuery, limit * 2);

    // 1.5 DF-zero 丢弃（D4）：AND 为空时用 DF-pruned AND 作为 AND 侧结果，
    //     之后的 OR 并集逻辑一字不动。
    if (hits.empty() && !tokens.empty()) {
        tryDfPrunedAnd(tokens, db_, limit, hits);
    }

    //    冲突时保留 AND 版本（先放入 AND，再追加 OR 中未见过的 doc_id）。
    if (!tokens.empty()) {
        const std::string orQuery =
            tokens.size() >= 2 ? buildOrMatchQuery(rest) : expandTokenOrSingle(tokens[0]);
        std::vector<Hit> orHits = db_.searchFts(orQuery, limit * 2);
        if (tokens.size() == 1) {
            // 单 token OR 召回偏宽，用 substringRecallPass 精确过滤（同 search 阶段 2）。
            std::vector<Hit> filtered;
            filtered.reserve(orHits.size());
            for (const Hit& h : orHits) {
                std::string hay = h.title;
                if (auto content = db_.getContentById(h.doc_id)) {
                    hay.push_back('\n');
                    hay += *content;
                } else {
                    hay += h.snippet;
                }
                if (substringRecallPass(hay, tokens)) filtered.push_back(h);
            }
            orHits = std::move(filtered);
            if (orHits.empty()) {
                // 第二击（同 search stage2）：第一击精滤全空时尝试 DF-zero 分解；
                // 仍空则 orHits 保持为空（原并集语义不变）。
                std::vector<Hit> second;
                if (tryCharDecomposedSingle(tokens[0], db_, limit, second)) {
                    orHits = std::move(second);
                }
            }
        }
        std::set<int64_t> seen;
        for (const Hit& h : hits) {
            seen.insert(h.doc_id);
        }
        for (const Hit& h : orHits) {
            if (seen.insert(h.doc_id).second) {
                hits.push_back(h);
            }
        }
    }

    // 3. 子串召回回退（T2 修复）：并集为空时，把中文 token 拆成单字
    //    做 OR 粗筛，再用"原文按 token 逐个包含查询子串"精验后保留。
    if (hits.empty()) {
        const std::string subQuery = buildSubstringRecallQuery(tokens);
        if (!subQuery.empty()) {
            std::vector<Hit> subHits = db_.searchFts(subQuery, limit * 2);
            for (const Hit& h : subHits) {
                std::string hay = h.title;
                if (auto content = db_.getContentById(h.doc_id)) {
                    hay.push_back('\n');
                    hay += *content;
                } else {
                    hay += h.snippet;
                }
                if (substringRecallPass(hay, tokens)) hits.push_back(h);
            }
        }
    }

    hits = filterByPhrases(std::move(hits), db_, phrases);
    return rerankHits(std::move(hits), tokens, query, weights_, limit, phrases, db_);
}

}  // namespace docseek
