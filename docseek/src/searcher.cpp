// src/searcher.cpp
#include "docseek/searcher.h"

#include <cctype>
#include <string>
#include <vector>

namespace docseek {

Searcher::Searcher(Database& db) : db_(db) {}

// 按空白分词，将每个 token 用双引号包裹（内部双引号转义为两个双引号），
// 用空格连接；无有效 token 时返回空字符串。
std::string Searcher::buildMatchQuery(const std::string& query) {
    std::vector<std::string> tokens;
    std::string current;
    for (char ch : query) {
        unsigned char uc = static_cast<unsigned char>(ch);
        if (std::isspace(uc)) {
            if (!current.empty()) {
                tokens.push_back(current);
                current.clear();
            }
        } else {
            current.push_back(ch);
        }
    }
    if (!current.empty()) {
        tokens.push_back(current);
    }

    if (tokens.empty()) {
        return std::string();
    }

    std::string result;
    for (size_t i = 0; i < tokens.size(); ++i) {
        if (i > 0) {
            result.push_back(' ');
        }
        result.push_back('"');
        for (char c : tokens[i]) {
            if (c == '"') {
                // 转义双引号为两个双引号
                result.append("\"\"");
            } else {
                result.push_back(c);
            }
        }
        result.push_back('"');
    }
    return result;
}

// 构建 FTS 匹配串后查询；空匹配串返回空结果；limit<=0 时默认 20。
std::vector<Hit> Searcher::search(const std::string& query, int limit) {
    std::string mq = buildMatchQuery(query);
    if (mq.empty()) {
        return {};
    }
    if (limit <= 0) {
        limit = 20;
    }
    return db_.searchFts(mq, limit);
}

}  // namespace docseek
