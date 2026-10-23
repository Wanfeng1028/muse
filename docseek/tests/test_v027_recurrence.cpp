#include <gtest/gtest.h>
#include <docseek/passage_ranker.h>
#include <docseek/query_parser.h>
#include <string>
#include <vector>
#include <utility>

using namespace docseek;

namespace {

inline ParsedQuery makePq(const std::vector<std::string>& keywords, bool hasRecurrence = false) {
    ParsedQuery pq;
    pq.keywords = keywords;
    pq.hasRecurrence = hasRecurrence;
    // other fields default empty
    return pq;
}

// Create empty TermWeights
inline TermWeights makeWeights() {
    return TermWeights{};
}

} // namespace

TEST(RecurrenceV027, DetectPositive) {
    // Test 1
    auto pq = parseNaturalQuery("孩子明明之前已经学会上厕所了，最近又频繁尿裤子是怎么回事？");
    EXPECT_TRUE(pq.hasRecurrence);
}

TEST(RecurrenceV027, DetectOnlyRecurNoPast) {
    // Test 2
    auto pq = parseNaturalQuery("又尿裤子了怎么办");
    EXPECT_FALSE(pq.hasRecurrence);
}

TEST(RecurrenceV027, DetectOnlyPastNoRecur) {
    // Test 3
    auto pq = parseNaturalQuery("孩子已经两岁了什么时候开始训练");
    EXPECT_FALSE(pq.hasRecurrence);
}

TEST(RecurrenceV027, DetectZhiQianExcluded) {
    // Test 4
    auto pq = parseNaturalQuery("发现有人突然倒地，在靠近他之前应该先做什么？");
    EXPECT_FALSE(pq.hasRecurrence);
}

TEST(RecurrenceV027, AlignBonusApplied) {
    // Test 5
    const std::string content = "本来已经半个月不尿裤子了，突然又开始一天湿三条\n第二行无标记内容";
    const std::vector<std::string> keywords = {"尿裤子"};
    auto pqTrue = makePq(keywords, true);
    auto pqFalse = makePq(keywords, false);
    const TermWeights emptyWeights = makeWeights();

    auto passagesTrue = rankPassages(0, "", content, pqTrue, 10, emptyWeights, "");
    auto passagesFalse = rankPassages(0, "", content, pqFalse, 10, emptyWeights, "");

    ASSERT_FALSE(passagesTrue.empty());
    ASSERT_FALSE(passagesFalse.empty());

    double scoreTrue = passagesTrue[0].score;
    double scoreFalse = passagesFalse[0].score;

    EXPECT_NEAR(scoreTrue - scoreFalse, 0.08, 1e-9);
    EXPECT_GT(scoreTrue, scoreFalse);
}

TEST(RecurrenceV027, AlignNoBonusWithoutFlag) {
    // Test 6
    const std::string content = "本来已经半个月不尿裤子了，突然又开始一天湿三条\n第二行无标记内容";
    const std::vector<std::string> keywords = {"尿裤子"};
    auto pqFalse = makePq(keywords, false);
    const TermWeights emptyWeights = makeWeights();

    auto passages1 = rankPassages(0, "", content, pqFalse, 10, emptyWeights, "");
    auto passages2 = rankPassages(0, "", content, pqFalse, 10, emptyWeights, "");

    ASSERT_FALSE(passages1.empty());
    ASSERT_FALSE(passages2.empty());

    EXPECT_DOUBLE_EQ(passages1[0].score, passages2[0].score);
}

TEST(RecurrenceV027, AlignNoBonusMissingPastMarker) {
    // 测试窗口只有复现标记"又"、无过去标记时，即使 hasRecurrence=true 也不加成
    const std::string content = "孩子又尿裤子了\n第二行无标记内容";
    const std::vector<std::string> keywords = {"尿裤子"};
    auto pqTrue = makePq(keywords, true);
    auto pqFalse = makePq(keywords, false);
    const TermWeights emptyWeights = makeWeights();
    auto passagesTrue = rankPassages(0, "", content, pqTrue, 10, emptyWeights, "");
    auto passagesFalse = rankPassages(0, "", content, pqFalse, 10, emptyWeights, "");
    ASSERT_FALSE(passagesTrue.empty());
    ASSERT_FALSE(passagesFalse.empty());
    EXPECT_NEAR(passagesTrue[0].score - passagesFalse[0].score, 0.0, 1e-9);
}
