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

// ===== v0.14 失败对回归测试 =====
// 每个用例对应本轮修好的一个评测对，注释说明 pair id 与"先红"依据。

// pair v08-qa-03「请问发货得几天啊」：修复前 keywords 含 "得"，
// NOT contains "得" 会红；修复后应只保留 ["发货","几天"]。
TEST(QueryParserV014, ColloquialShippingQueryDropsDe) {
    const ParsedQuery parsed = parseNaturalQuery("请问发货得几天啊");
    EXPECT_TRUE(contains(parsed.keywords, "发货"));
    EXPECT_TRUE(contains(parsed.keywords, "几天"));
    EXPECT_FALSE(contains(parsed.keywords, "得"));
    EXPECT_FALSE(contains(parsed.keywords, "请问"));
    EXPECT_FALSE(contains(parsed.keywords, "啊"));
}

// pair v08-qa-09「我想知道数据应该多久备份一次才比较合适，请问有没有建议」：
// 修复前 keywords 含 "我想知道" 的组成词、"应该"、"才"、"比较合适" 的组成词、
// "建议"、全角 "，"，这些 NOT contains 会红；修复后应只保留 ["数据","多久","备份","一次"]。
TEST(QueryParserV014, LongColloquialAdviceQueryDropsFillersAndPunct) {
    const ParsedQuery parsed =
        parseNaturalQuery("我想知道数据应该多久备份一次才比较合适，请问有没有建议");
    EXPECT_TRUE(contains(parsed.keywords, "数据"));
    EXPECT_TRUE(contains(parsed.keywords, "多久"));
    EXPECT_TRUE(contains(parsed.keywords, "备份"));
    EXPECT_TRUE(contains(parsed.keywords, "一次"));
    EXPECT_FALSE(contains(parsed.keywords, "我想知道"));
    EXPECT_FALSE(contains(parsed.keywords, "应该"));
    EXPECT_FALSE(contains(parsed.keywords, "才"));
    EXPECT_FALSE(contains(parsed.keywords, "比较合适"));
    EXPECT_FALSE(contains(parsed.keywords, "有没有建议"));
    EXPECT_FALSE(contains(parsed.keywords, "建议"));
    EXPECT_FALSE(contains(parsed.keywords, "，"));
    EXPECT_FALSE(contains(parsed.keywords, "请问"));
}

// pair v08-qa-10「请问你们有哪些套餐，我该怎么选呢」：修复前 keywords 为
// ["你们","套餐","，","我","该","选"]，故 "你们"/"，"/"我"/"该" 的 NOT contains 会红；
// 修复后应只保留 ["套餐","选"]。
TEST(QueryParserV014, PackageSelectionQueryDropsPronounsAndPunct) {
    const ParsedQuery parsed = parseNaturalQuery("请问你们有哪些套餐，我该怎么选呢");
    EXPECT_TRUE(contains(parsed.keywords, "套餐"));
    EXPECT_TRUE(contains(parsed.keywords, "选"));
    EXPECT_FALSE(contains(parsed.keywords, "你们"));
    EXPECT_FALSE(contains(parsed.keywords, "我"));
    EXPECT_FALSE(contains(parsed.keywords, "该"));
    EXPECT_FALSE(contains(parsed.keywords, "，"));
    EXPECT_FALSE(contains(parsed.keywords, "请问"));
    EXPECT_FALSE(contains(parsed.keywords, "哪些"));
    EXPECT_FALSE(contains(parsed.keywords, "怎么"));
    EXPECT_FALSE(contains(parsed.keywords, "呢"));
}

// pair v08-qa-15「想找客服，联系方式在哪啊」：修复前 keywords 为
// ["想","找","客服","，","联系","方式","联系方式"]，"想" 与 "，" 的 NOT contains 会红；
// 注意「找」经 A9 审计决定不进 fillerWords，修复后仍含 "找"，故不断言 NOT contains "找"。
TEST(QueryParserV014, ContactLookupQueryDropsXiangAndPunct) {
    const ParsedQuery parsed = parseNaturalQuery("想找客服，联系方式在哪啊");
    EXPECT_TRUE(contains(parsed.keywords, "客服"));
    EXPECT_TRUE(contains(parsed.keywords, "联系"));
    EXPECT_TRUE(contains(parsed.keywords, "联系方式"));
    EXPECT_FALSE(contains(parsed.keywords, "想"));
    EXPECT_FALSE(contains(parsed.keywords, "，"));
    EXPECT_FALSE(contains(parsed.keywords, "在哪"));
    EXPECT_FALSE(contains(parsed.keywords, "啊"));
}

// 全角标点通用回归：修复前全角 "，"、"。"、"？" 会进 keywords，
// 对应的 NOT contains 会红；修复后标点应被清除，核心词保留。
TEST(QueryParserV014, FullWidthPunctuationStripped) {
    const ParsedQuery parsed = parseNaturalQuery("套餐，价格。多少？");
    EXPECT_FALSE(contains(parsed.keywords, "，"));
    EXPECT_FALSE(contains(parsed.keywords, "。"));
    EXPECT_FALSE(contains(parsed.keywords, "？"));
    EXPECT_TRUE(contains(parsed.keywords, "套餐"));
    EXPECT_TRUE(contains(parsed.keywords, "价格"));
}

// v0.15 fillerWords 回归：D 类 t007-q11「什么时候」穿透，应被丢弃。
TEST(QueryParserV015, FillerWordsV015DropsNoise) {
    auto k1 = parseNaturalQuery("自由泳换气的时候头应该什么时候转过去").keywords;
    EXPECT_FALSE(contains(k1, "什么时候"));
    EXPECT_FALSE(contains(k1, "什么"));

    auto k2 = parseNaturalQuery("长期不弹琴的话，琴弦应该怎么处理比较好").keywords;
    EXPECT_FALSE(contains(k2, "的话"));
    EXPECT_FALSE(contains(k2, "比较"));
    EXPECT_TRUE(contains(k2, "琴弦"));

    auto k3 = parseNaturalQuery("怕水怎么办").keywords;
    EXPECT_FALSE(contains(k3, "怎么办"));
}

// v0.15 否定语义保护：「不」字永不入表，不能把「不建议」误拆成「建议」。
TEST(QueryParserV015, NegationBuIsPreserved) {
    auto k = parseNaturalQuery("不建议熬夜").keywords;
    EXPECT_TRUE(contains(k, "不建议") || contains(k, "不"));
}

}  // namespace
}  // namespace docseek