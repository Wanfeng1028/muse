#include <gtest/gtest.h>
#include "docseek/passage_ranker.h"
#include "docseek/query_parser.h"

using namespace docseek;

namespace {
// Helper to construct a ParsedQuery from a keyword list.
ParsedQuery makePq(std::vector<std::string> kws) {
    ParsedQuery pq;
    pq.keywords = std::move(kws);
    return pq;
}

// Helper to construct TermWeights from a list of (term, weight) pairs.
TermWeights makeWeights(std::vector<std::pair<std::string, double>> kvs) {
    TermWeights w;
    for (auto& kv : kvs) w.weights[kv.first] = kv.second;
    return w;
}
}

// 测试 parseNaturalQuery 的 asksRange 标记
TEST(ParseNaturalQuery, AsksRangeFlag) {
    // “范围/多少/多久/多长/多大/几/多高/多宽/多厚” 任一出现应设为 true
    EXPECT_TRUE(parseNaturalQuery("这本书大概多少页？").asksRange);
    EXPECT_FALSE(parseNaturalQuery("今天天气怎么样").asksRange);
}

// 辅助函数：在给定的 content / keywords/weights 下，获取 rankPassages 的结果
static std::vector<Passage> runRank(bool asksRangeFlag) {
    // 所有测试共用同一份内容、关键词和权重，以保证评分仅因 asksRange 而异
    const std::string content = "甲说二十分钟乙说四十分钟丙说十分钟";
    const std::vector<std::string> keywords = {"甲"};
    const TermWeights weights = makeWeights({{"甲", 1.0}});
    ParsedQuery pq = makePq(keywords);
    pq.asksRange = asksRangeFlag;
    // doc_id 和 path 可随意，title 设为空
    return rankPassages(1, "dummy/path", content, pq, 5, weights, "");
}

// 连续测试 Chinese numeral+unit 加成，比较 asksRange true/false 的评分差值
TEST(ChineseNumeralRangeAdd, ThreeHits) {
    auto rankedTrue  = runRank(true);
    auto rankedFalse = runRank(false);
    ASSERT_GE(rankedTrue.size(), 1u);
    ASSERT_GE(rankedFalse.size(), 1u);
    // 由于中文数字+单位出现了 3 个命中，应加 0.08
    EXPECT_NEAR(rankedTrue[0].score - rankedFalse[0].score, 0.08, 1e-9);
}

TEST(ChineseNumeralRangeAdd, TwoHits) {
    // 此测试使用不同的 content，其中中文数字+单位只出现两次
    const std::string content = "甲说二十分钟乙说五分钟";
    const std::vector<std::string> keywords = {"甲"};
    const TermWeights weights = makeWeights({{"甲", 1.0}});
    auto run = [&](bool flag) {
        ParsedQuery pq = makePq(keywords);
        pq.asksRange = flag;
        return rankPassages(1, "dummy/path", content, pq, 5, weights, "");
    };
    auto rankedTrue = run(true);
    auto rankedFalse = run(false);
    ASSERT_GE(rankedTrue.size(), 1u);
    ASSERT_GE(rankedFalse.size(), 1u);
    // 两个中文数字+单位，不应产生加成
    EXPECT_NEAR(rankedTrue[0].score - rankedFalse[0].score, 0.0, 1e-9);
}

TEST(ChineseNumeralRangeAdd, TwoArabicHits) {
    const std::string content = "甲说20分钟乙说40分钟";
    const std::vector<std::string> keywords = {"甲"};
    const TermWeights weights = makeWeights({{"甲", 1.0}});
    auto run = [&](bool flag) {
        ParsedQuery pq = makePq(keywords);
        pq.asksRange = flag;
        return rankPassages(1, "dummy/path", content, pq, 5, weights, "");
    };
    auto rankedTrue = run(true);
    auto rankedFalse = run(false);
    ASSERT_GE(rankedTrue.size(), 1u);
    ASSERT_GE(rankedFalse.size(), 1u);
    // 两个阿拉伯数字+单位，保留原有加成行为
    EXPECT_NEAR(rankedTrue[0].score - rankedFalse[0].score, 0.08, 1e-9);
}

TEST(ChineseNumeralRangeAdd, MixedDigits) {
    const std::string content = "甲说20分钟乙说二十分钟丙说三分钟";
    const std::vector<std::string> keywords = {"甲"};
    const TermWeights weights = makeWeights({{"甲", 1.0}});
    auto run = [&](bool flag) {
        ParsedQuery pq = makePq(keywords);
        pq.asksRange = flag;
        return rankPassages(1, "dummy/path", content, pq, 5, weights, "");
    };
    auto rankedTrue = run(true);
    auto rankedFalse = run(false);
    ASSERT_GE(rankedTrue.size(), 1u);
    ASSERT_GE(rankedFalse.size(), 1u);
    // 1 个阿拉伯 + 2 个中文，不合并计算，不应加成
    EXPECT_NEAR(rankedTrue[0].score - rankedFalse[0].score, 0.0, 1e-9);
}

TEST(ChineseNumeralRangeAdd, DecimalChinese) {
    const std::string content = "零点五克糖零点三克盐泡十分钟";
    const std::vector<std::string> keywords = {"甲"};
    const TermWeights weights = makeWeights({{"甲", 1.0}});
    auto run = [&](bool flag) {
        ParsedQuery pq = makePq(keywords);
        pq.asksRange = flag;
        return rankPassages(1, "dummy/path", content, pq, 5, weights, "");
    };
    auto rankedTrue = run(true);
    auto rankedFalse = run(false);
    ASSERT_GE(rankedTrue.size(), 1u);
    ASSERT_GE(rankedFalse.size(), 1u);
    // 零点五 / 零点三 / 十分钟，共 3 个中文数字+单位，应加 0.08
    EXPECT_NEAR(rankedTrue[0].score - rankedFalse[0].score, 0.08, 1e-9);
}
