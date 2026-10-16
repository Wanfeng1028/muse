#include "docseek/searcher.h"

#include "docseek/token_locate.h"

#include "docseek/query_parser.h"
#include "docseek/jieba_tokenizer.h"

#include <algorithm>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace docseek {
namespace {

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
std::string expandTokenOrQuery(const std::string& token) {
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
    size_t expected = 0;
    for (const std::string& w : words) {
        if (!w.empty()) ++expected;
    }
    if (located.size() != expected) {
        return quoteToken(token);  // 定位失败，退化为原文
    }
    std::map<size_t, std::vector<std::string>> groups;
    for (const LocatedToken& lt : located) {
        std::vector<std::string>& g = groups[lt.byteOffset];
        if (std::find(g.begin(), g.end(), lt.word) == g.end()) {
            g.push_back(lt.word);
        }
    }
    if (groups.empty()) {
        return quoteToken(token);
    }

    // 把一组词转成查询片段：单成员直接引号，多成员 OR。
    auto groupExpr = [](const std::vector<std::string>& g) {
        if (g.size() == 1) return quoteToken(g[0]);
        std::string e = "(";
        for (size_t i = 0; i < g.size(); ++i) {
            if (i > 0) e += " OR ";
            e += quoteToken(g[i]);
        }
        e += ")";
        return e;
    };

    if (groups.size() == 1) {
        const std::vector<std::string>& g = groups.begin()->second;
        if (g.size() == 1) {
            return quoteToken(token);  // 与原来一字不差
        }
        return groupExpr(g);
    }

    std::string out;
    for (const auto& kv : groups) {
        if (!out.empty()) out += " AND ";
        out += groupExpr(kv.second);
    }
    return out;
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

std::vector<Hit> Searcher::search(const std::string& query, int limit) {
    if (query.empty() || limit <= 0) {
        return {};
    }

    const std::vector<std::string> tokens = splitTokens(query);
    if (tokens.empty()) {
        // 查询只有空白字符，视为空查询。
        return {};
    }

    // 1. 精确 AND：多取 2 倍做重排。
    const std::string matchQuery = buildMatchQuery(query);
    std::vector<Hit> hits = db_.searchFts(matchQuery, limit * 2);

    // 2. OR 回退：AND 无结果且 token 数 >= 2 时放宽为 OR。
    if (hits.empty() && tokens.size() >= 2) {
        const std::string orQuery = buildOrMatchQuery(query);
        hits = db_.searchFts(orQuery, limit * 2);
    }

    // 3. 子串召回回退（T2 修复）：AND 与 OR 都无结果时，把中文 token 拆成单字
    //    做 OR 粗筛，再用"原文按 token 逐个包含查询子串"精验后保留。
    //    jieba 最长匹配受上下文影响，查询词（如"猫砂"）在索引词汇表中不存在，
    //    但其单字（如"猫"）通常在索引里。纯单字 OR 会过度召回（如"量子纠缠"
    //    的"量/子"遍地都是），因此只保留原文（或标题）中确实连续包含每个
    //    查询 token 的文档——这正是"子串查询"的定义。本阶段只在前两阶段都
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
                bool allFound = true;
                for (const std::string& t : tokens) {
                    if (!containsFolded(hay, t)) { allFound = false; break; }
                }
                if (allFound) hits.push_back(h);
            }
        }
    }

    if (hits.empty()) {
        return {};
    }

    // 4. 重排序：bm25 基础分 + title 加成 + 短语加成。
    const std::string longQuery = removeWhitespace(query);

    for (Hit& hit : hits) {
        double finalScore = hit.score;  // base = -bm25，越大越相关

        // title 加成：每个 query token 在 title 中出现为子串，+1.0。
        for (const std::string& token : tokens) {
            if (hit.title.find(token) != std::string::npos) {
                finalScore += weights_.titleBoost;
            }

        }

        // 短语加成：去掉空白的连续查询串出现在 title 或 snippet 中，+2.0。
        if (!longQuery.empty()) {
            if (hit.title.find(longQuery) != std::string::npos ||
                hit.snippet.find(longQuery) != std::string::npos) {
                finalScore += weights_.phraseBoost;
            }

        }

        hit.score = finalScore;
    }

    // 按总分降序排序。
    std::stable_sort(hits.begin(), hits.end(),
                     [](const Hit& a, const Hit& b) { return a.score > b.score; });

    // 截断到 limit。
    if (static_cast<int>(hits.size()) > limit) {
        hits.resize(static_cast<size_t>(limit));
    }

    return hits;
}

}  // namespace docseek
