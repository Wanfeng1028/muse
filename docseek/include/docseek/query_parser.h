#pragma once

#include <string>
#include <vector>

namespace docseek {

// 自然语言查询解析结果。
struct ParsedQuery {
    std::vector<std::string> keywords;  // 去重保序
    std::vector<std::string> phrases;   // 引号短语，去重保序
    bool passageIntent = false;         // 是否明确要"段落/原文"
};

// 解析自然语言查询：抽取引号短语、删除疑问/语气词、jieba 分词过滤、兜底切分。
// 空输入（去空白后为空）返回空 ParsedQuery。
ParsedQuery parseNaturalQuery(const std::string& raw);

// 判断是否为单字中文停用词（查询展开等复用）。
bool isSingleCharStopword(const std::string& w);

// 抽取引号短语：支持 "..."、「...」、“...” 三种配对引号。
// phrases 输出去重保序的短语；rest 输出移除短语后的剩余文本。
// 未闭合的引号按普通字符保留在 rest 中。
void extractPhrases(const std::string& in, std::vector<std::string>& phrases,
                    std::string& rest);

}  // namespace docseek
