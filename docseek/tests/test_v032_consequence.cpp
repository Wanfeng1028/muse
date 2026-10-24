#include <gtest/gtest.h>
#include <docseek/passage_ranker.h>
#include <docseek/query_parser.h>
#include <string>
#include <vector>
using namespace docseek;

TEST(ConsequenceV032, DetectPositive) {
    ParsedQuery pq = parseNaturalQuery("撒放时手指主动张开会带来什么后果？");
    EXPECT_TRUE(pq.asksConsequence);
}

TEST(ConsequenceV032, DetectLeadTo) {
    ParsedQuery pq = parseNaturalQuery("这样做会导致什么问题");
    EXPECT_TRUE(pq.asksConsequence);
}

TEST(ConsequenceV032, DetectImpact) {
    ParsedQuery pq = parseNaturalQuery("长期熬夜对身体有什么影响");
    EXPECT_TRUE(pq.asksConsequence);
}

TEST(ConsequenceV032, DetectNonePlain) {
    ParsedQuery pq = parseNaturalQuery("今天天气怎么样");
    EXPECT_FALSE(pq.asksConsequence);
}

TEST(ConsequenceV032, DetectNoneKeywordQuery) {
    ParsedQuery pq = parseNaturalQuery("三色激光散斑");
    EXPECT_FALSE(pq.asksConsequence);
}

TEST(ConsequenceV032, BonusApplied) {
    std::string content = "撒放时手指主动张开\n主动张手会让箭尾左右摆动";
    ParsedQuery pq_true;
    pq_true.keywords = {"撒放", "手指"};
    pq_true.asksConsequence = true;
    auto passages_true = rankPassages(0, "", content, pq_true, 10, TermWeights{}, "");
    ASSERT_FALSE(passages_true.empty());
    ParsedQuery pq_false;
    pq_false.keywords = {"撒放", "手指"};
    pq_false.asksConsequence = false;
    auto passages_false = rankPassages(0, "", content, pq_false, 10, TermWeights{}, "");
    ASSERT_FALSE(passages_false.empty());
    EXPECT_NEAR(passages_true[0].score - passages_false[0].score, 0.08, 1e-9);
}

TEST(ConsequenceV032, NoBonusWithoutMarker) {
    std::string content = "撒放时手指主动张开，而不是自然放松滑弦\n第二行内容";
    ParsedQuery pq_true;
    pq_true.keywords = {"撒放", "手指"};
    pq_true.asksConsequence = true;
    auto passages_true = rankPassages(0, "", content, pq_true, 10, TermWeights{}, "");
    ASSERT_FALSE(passages_true.empty());
    ParsedQuery pq_false;
    pq_false.keywords = {"撒放", "手指"};
    pq_false.asksConsequence = false;
    auto passages_false = rankPassages(0, "", content, pq_false, 10, TermWeights{}, "");
    ASSERT_FALSE(passages_false.empty());
    EXPECT_NEAR(passages_true[0].score, passages_false[0].score, 1e-9);
}

TEST(ConsequenceV032, MultipleMarkersSingleBonus) {
    std::string content = "撒放手指练习记录\n这样做会让进度变慢，还会导致返工";
    ParsedQuery pq_true;
    pq_true.keywords = {"撒放", "手指"};
    pq_true.asksConsequence = true;
    auto passages_true = rankPassages(0, "", content, pq_true, 10, TermWeights{}, "");
    ASSERT_FALSE(passages_true.empty());
    ParsedQuery pq_false;
    pq_false.keywords = {"撒放", "手指"};
    pq_false.asksConsequence = false;
    auto passages_false = rankPassages(0, "", content, pq_false, 10, TermWeights{}, "");
    ASSERT_FALSE(passages_false.empty());
    EXPECT_NEAR(passages_true[0].score - passages_false[0].score, 0.08, 1e-9);
}