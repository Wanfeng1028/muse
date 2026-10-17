// tests/test_query_parser.cpp
// 针对 docseek v0.12 parseNaturalQuery 的单元测试
#include <gtest/gtest.h>

#include <string>
#include <vector>

#include "docseek/query_parser.h"

namespace docseek {
namespace {

// 判断 vector 中是否包含指定字符串
bool contains(const std::vector<std::string>& vec, const std::string& value) {
    for (const auto& item : vec) {
        if (item == value) {
            return true;
        }
    }
    return false;
}

// 尾部谓语剥离：应剥掉 "哪一段" 与尾部 "写在"，保留核心关键词
TEST(QueryParserV012, TrailingPredicateStripping) {
    const ParsedQuery parsed = parseNaturalQuery("退款流程写在哪一段");
    EXPECT_TRUE(contains(parsed.keywords, "退款"));
    EXPECT_TRUE(contains(parsed.keywords, "流程"));
    EXPECT_FALSE(contains(parsed.keywords, "写"));
    EXPECT_FALSE(contains(parsed.keywords, "写在"));
    EXPECT_FALSE(contains(parsed.keywords, "哪一段"));
    EXPECT_TRUE(parsed.passageIntent);
}

// FAQ 尾部剥离：疑问词与尾部 "说明" 都应被剥掉
TEST(QueryParserV012, FaqTailStripping) {
    const ParsedQuery parsed = parseNaturalQuery("发货说明在哪里");
    EXPECT_TRUE(contains(parsed.keywords, "发货"));
    EXPECT_FALSE(contains(parsed.keywords, "说明"));
    EXPECT_FALSE(contains(parsed.keywords, "在哪里"));
}

// filler 表按长度降序删除："在哪里" 先于 "在哪"，两种问法结果应一致
TEST(QueryParserV012, FillerLengthDescEquivalence) {
    const ParsedQuery shortForm = parseNaturalQuery("退款流程写在哪");
    const ParsedQuery longForm = parseNaturalQuery("退款流程写在哪里");
    EXPECT_EQ(shortForm.keywords, longForm.keywords);
    EXPECT_EQ(shortForm.phrases, longForm.phrases);
}

// 空输入（含纯空白）应直接返回空的 ParsedQuery
TEST(QueryParserV012, EmptyInput) {
    const ParsedQuery empty = parseNaturalQuery("");
    EXPECT_TRUE(empty.keywords.empty());
    EXPECT_TRUE(empty.phrases.empty());

    const ParsedQuery blank = parseNaturalQuery("   ");
    EXPECT_TRUE(blank.keywords.empty());
    EXPECT_TRUE(blank.phrases.empty());
}

// 普通关键词：无 filler、无尾部谓语，应保留分词结果且无段落意图
TEST(QueryParserV012, PlainKeywordUnchanged) {
    const ParsedQuery parsed = parseNaturalQuery("智能手机");
    EXPECT_FALSE(parsed.keywords.empty());
    EXPECT_TRUE(contains(parsed.keywords, "智能手机"));
    EXPECT_FALSE(parsed.passageIntent);
}

}  // namespace
}  // namespace docseek