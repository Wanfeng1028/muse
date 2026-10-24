#pragma once

#include <string>
#include <vector>

namespace docseek {

// 自然语言查询解析结果。
struct ParsedQuery {
    std::vector<std::string> keywords;  // 去重保序
    std::vector<std::string> phrases;   // 引号短语，去重保序
    std::vector<std::string> reconstructedCompounds;  // 理解层重构的复合概念候选，去重保序
    bool passageIntent = false;         // 是否明确要"段落/原文"
    bool hasRecurrence = false;         // 查询是否含"过去状态→近期复现"结构（过去标记与复现标记同时出现）
    bool asksRange = false;             // 查询是否为"索取数值范围/数量"型问句（在 raw 上判定，见 detectRangeIntent）
    bool asksConsequence = false;       // 查询是否为"索取后果/结果"型问句（在 raw 上判定，见 detectConsequenceIntent）
    bool asksSafety = false;            // 查询是否为"安全关切"型问句（在 raw 上判定，见 detectSafetyConcern）
    std::string querySubjectNo;         // 查询中的明确科目编号（"一".."十"），如"科目一"→"一"；无则空串（v0.31.0，见 detectSubjectNo）
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

// 剥离疑问/语气词（复用 fillerWords 表），供 search/searchQuestion 查询构建调用，
// 与 parseNaturalQuery 的过滤行为对齐；"不"永不入表，否定语义保留；空输入返回空。
std::string stripFillerWords(const std::string& raw);

// 从定位类问句中抽取用户真正想找的目标短语。
// 识别顺序：①引号短语优先（复用 extractPhrases，支持 "..." / 「...」/ “...”）；
// ②「提到/写到/说到/讲到/谈到/介绍」之后、「的那段/的那句/的那部分/在哪里/在哪/哪里/哪一段/是什么/吗/?/？/。」之前；
// ③「写在哪/在哪/哪里/何处」之前，剥离前导疑问词（请问/请告诉我/帮我找/找出/查找/搜索/那个/这个）后剩余的核心词；
// ④都抽不到返回空串。全部基于 std::string::find 的 UTF-8 字节匹配，不依赖 ICU。
std::string extractLocateTarget(const std::string& raw);

}  // namespace docseek
