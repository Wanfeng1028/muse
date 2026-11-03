#include <gtest/gtest.h>
#include <string>
#include <vector>
#include "docseek/query_parser.h"

namespace docseek {
namespace {

bool contains(const std::vector<std::string>& vec, const std::string& value) {
    for (const auto& item : vec) { if (item == value) return true; }
    return false;
}

TEST(QueryParserV017, TrailingBuAfterQuestionMarkStripped) {
    auto k = parseNaturalQuery("这个方案靠谱不？").keywords;
    EXPECT_FALSE(contains(k, "不"));
}

TEST(QueryParserV017, TrailingBuAfterPeriodStripped) {
    auto k = parseNaturalQuery("这样备份才算稳妥不。").keywords;
    EXPECT_FALSE(contains(k, "不"));
}

TEST(QueryParserV017, TrailingBuAfterExclamationStripped) {
    auto k = parseNaturalQuery("快点备份不！").keywords;
    EXPECT_FALSE(contains(k, "不"));
}

TEST(QueryParserV017, DeBuEndingProtected) {
    auto k = parseNaturalQuery("你不得不同意这个方案").keywords;
    EXPECT_TRUE(contains(k, "不得不") || contains(k, "不"));
}

TEST(QueryParserV017, MidBuYaoUntouched) {
    auto k = parseNaturalQuery("不要熬夜对身体不好吗").keywords;
    EXPECT_TRUE(contains(k, "不要") || contains(k, "不"));
}

TEST(QueryParserV017, TrailingBuShortQuery) {
    auto k = parseNaturalQuery("行不行").keywords;
    EXPECT_FALSE(contains(k, "不"));
}

}  // namespace
}  // namespace docseek
