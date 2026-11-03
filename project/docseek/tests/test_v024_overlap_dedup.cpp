#include <gtest/gtest.h>
#include "docseek/passage_ranker.h"
#include "docseek/query_parser.h"

#include <string>
#include <vector>

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

}  // namespace

// v0.24.0 重叠感知计分：复合词展开的重叠关键词在同一 span 上只计一次（归最长者）。
TEST(OverlapDedup, CompoundClaimsSpanOnce) {
    ParsedQuery pq = makePq({"过敏", "反应", "过敏反应"});
    TermWeights w = makeWeights({{"过敏", 1.0}, {"反应", 1.0}, {"过敏反应", 1.0}});
    std::string content = "第一行\n患者出现过敏反应需处理\n第三行";
    auto result = rankPassages(1, "test.txt", content, pq, 10, w);
    ASSERT_EQ(result.size(), 1u);
    ASSERT_EQ(result[0].matched_terms.size(), 1u);
    EXPECT_EQ(result[0].matched_terms[0], "过敏反应");
    // coverage=1/3, hitsTerm=1/8, posTerm=1.0；无短语/复合/数值/同义词加成。
    EXPECT_DOUBLE_EQ(result[0].score, 0.5 * (1.0 / 3.0) + 0.3 * 0.125 + 0.05 * 1.0);
}

TEST(OverlapDedup, SeparateOccurrencesStillCount) {
    ParsedQuery pq = makePq({"过敏", "反应", "过敏反应"});
    TermWeights w = makeWeights({{"过敏", 1.0}, {"反应", 1.0}, {"过敏反应", 1.0}});
    std::string content = "过敏很常见\n反应要迅速";
    auto result = rankPassages(1, "test.txt", content, pq, 10, w);
    ASSERT_EQ(result.size(), 1u);
    ASSERT_EQ(result[0].matched_terms.size(), 2u);
    EXPECT_EQ(result[0].matched_terms[0], "过敏");
    EXPECT_EQ(result[0].matched_terms[1], "反应");
    EXPECT_DOUBLE_EQ(result[0].score, 0.5 * (2.0 / 3.0) + 0.3 * 0.25 + 0.05 * 1.0);
}

TEST(OverlapDedup, PartialOverlapMixed) {
    ParsedQuery pq = makePq({"过敏", "反应", "过敏反应"});
    TermWeights w = makeWeights({{"过敏", 1.0}, {"反应", 1.0}, {"过敏反应", 1.0}});
    std::string content = "出现过敏反应后\n过敏史要询问";
    auto result = rankPassages(1, "test.txt", content, pq, 10, w);
    ASSERT_EQ(result.size(), 1u);
    // "反应"的唯一 span 被复合词覆盖；"过敏"在第二行有独立 span。
    ASSERT_EQ(result[0].matched_terms.size(), 2u);
    EXPECT_EQ(result[0].matched_terms[0], "过敏反应");
    EXPECT_EQ(result[0].matched_terms[1], "过敏");
    EXPECT_DOUBLE_EQ(result[0].score, 0.5 * (2.0 / 3.0) + 0.3 * 0.25 + 0.05 * 1.0);
}

TEST(OverlapDedup, SynonymFallbackPreserved) {
    ParsedQuery pq = makePq({"琴弦"});
    TermWeights w = makeWeights({{"琴弦", 2.0}});
    std::string content = "第一行\n把弦放松半音\n第三行";
    auto result = rankPassages(1, "test.txt", content, pq, 10, w);
    ASSERT_EQ(result.size(), 1u);
    ASSERT_EQ(result[0].matched_terms.size(), 1u);
    EXPECT_EQ(result[0].matched_terms[0], "琴弦");
    // 同义词命中：coverage=1.0, hitsTerm=0, posTerm=1.0, +kSynonymHitBonus 0.08。
    EXPECT_DOUBLE_EQ(result[0].score, 0.5 * 1.0 + 0.05 * 1.0 + 0.08);
}

TEST(OverlapDedup, OccurrenceCountingUnchanged) {
    ParsedQuery pq = makePq({"过敏"});
    TermWeights w = makeWeights({{"过敏", 2.0}});
    std::string content = "过敏\n过敏\n过敏";
    auto result = rankPassages(1, "test.txt", content, pq, 10, w);
    ASSERT_EQ(result.size(), 1u);
    ASSERT_EQ(result[0].matched_terms.size(), 1u);
    EXPECT_EQ(result[0].matched_terms[0], "过敏");
    // totalHitsWeighted=6.0 → hitsTerm=min(1,6/8)=0.75，出现次数计数语义不变。
    EXPECT_DOUBLE_EQ(result[0].score, 0.5 * 1.0 + 0.3 * 0.75 + 0.05 * 1.0);
}
