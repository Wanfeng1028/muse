#include <gtest/gtest.h>
#include "docseek/passage_ranker.h"
#include "docseek/query_parser.h"
#include <string>
#include <vector>
#include <utility>

using namespace docseek;

namespace {

ParsedQuery makePq(std::vector<std::string> kws) {
    ParsedQuery pq;
    pq.keywords = std::move(kws);
    return pq;
}

TermWeights makeWeights(std::vector<std::pair<std::string, double>> kvs) {
    TermWeights w;
    for (auto& kv : kvs) w.weights[kv.first] = kv.second;
    return w;
}

} // namespace

TEST(RareTermBonus, BonusApplied) {
    // 测试 idf>=6 时稀有词命中加成 0.05
    const std::string content = "甲继承乙\n丙行\n丁行";
    auto pq = makePq({"继承"});
    auto w = makeWeights({{"继承", 4.5374}});
    auto ranked = rankPassages(1, "t.txt", content, pq, 10, w, "");
    ASSERT_GE(ranked.size(), 1u);
    EXPECT_DOUBLE_EQ(ranked[0].score, 0.7701525);
}

TEST(RareTermBonus, NoBonusBelowThreshold) {
    // 测试 idf<6 时无加成
    const std::string content = "甲继承乙\n丙行\n丁行";
    auto pq = makePq({"继承"});
    auto w = makeWeights({{"继承", 0.7}});
    auto ranked = rankPassages(1, "t.txt", content, pq, 10, w, "");
    ASSERT_GE(ranked.size(), 1u);
    EXPECT_DOUBLE_EQ(ranked[0].score, 0.42625);
}

TEST(RareTermBonus, CappedAtFourTerms) {
    // 测试四个稀有词时加成封顶 0.15
    const std::string content = "继承转让赠与过户\n";
    auto pq = makePq({"继承", "转让", "赠与", "过户"});
    auto w = makeWeights({
        {"继承", 4.5374},
        {"转让", 4.5374},
        {"赠与", 4.5374},
        {"过户", 4.5374}
    });
    auto ranked = rankPassages(1, "t.txt", content, pq, 10, w, "");
    ASSERT_GE(ranked.size(), 1u);
    EXPECT_DOUBLE_EQ(ranked[0].score, 1.25);
}

TEST(RareTermBonus, EmptyWeightsNoCrash) {
    // 测试 TermWeights 为空时无加成且不会崩溃
    const std::string content = "甲继承乙\n";
    auto pq = makePq({"继承"});
    auto w = makeWeights({});
    auto ranked = rankPassages(1, "t.txt", content, pq, 10, w, "");
    ASSERT_GE(ranked.size(), 1u);
    EXPECT_DOUBLE_EQ(ranked[0].score, 0.5875);
}

TEST(RareTermBonus, ThreeTermsExactCap) {
    // 测试三个稀有词时加成恰等于封顶值 0.15
    const std::string content = "继承转让赠与\n";
    auto pq = makePq({"继承", "转让", "赠与"});
    auto w = makeWeights({
        {"继承", 4.5374},
        {"转让", 4.5374},
        {"赠与", 4.5374}
    });
    auto ranked = rankPassages(1, "t.txt", content, pq, 10, w, "");
    ASSERT_GE(ranked.size(), 1u);
    EXPECT_DOUBLE_EQ(ranked[0].score, 1.25);
}

TEST(RareTermBonus, BoundaryDf5NoBonus) {
    // df=5 主题词 idf=6.08 低于 6.2 阈值，不加分；锁定 v09-t048-q09 回归修复的阈值语义
    const std::string content = "甲青旅乙\n丙行\n丁行";
    auto pq = makePq({"青旅"});
    auto w = makeWeights({{"青旅", 4.2532}});
    auto ranked = rankPassages(1, "t.txt", content, pq, 10, w, "");
    ASSERT_GE(ranked.size(), 1u);
    EXPECT_DOUBLE_EQ(ranked[0].score, 0.7094950000);
}