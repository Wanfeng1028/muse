#include "docseek/searcher.h"

#include <algorithm>
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

std::string Searcher::buildMatchQuery(const std::string& query) {
    const std::vector<std::string> tokens = splitTokens(query);
    std::string out;
    for (size_t i = 0; i < tokens.size(); ++i) {
        if (i > 0) {
            out.push_back(' ');
        }
        out += quoteToken(tokens[i]);
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
        out += quoteToken(tokens[i]);
    }
    return out;
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

    if (hits.empty()) {
        return {};
    }

    // 3. 重排序：bm25 基础分 + title 加成 + 短语加成。
    const std::string longQuery = removeWhitespace(query);

    for (Hit& hit : hits) {
        double finalScore = hit.score;  // base = -bm25，越大越相关

        // title 加成：每个 query token 在 title 中出现为子串，+1.0。
        for (const std::string& token : tokens) {
            if (hit.title.find(token) != std::string::npos) {
                finalScore += 1.0;
            }
        }

        // 短语加成：去掉空白的连续查询串出现在 title 或 snippet 中，+2.0。
        if (!longQuery.empty()) {
            if (hit.title.find(longQuery) != std::string::npos ||
                hit.snippet.find(longQuery) != std::string::npos) {
                finalScore += 2.0;
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
