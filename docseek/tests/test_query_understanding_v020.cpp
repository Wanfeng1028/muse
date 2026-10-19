// tests/test_query_understanding_v020.cpp
#include <gtest/gtest.h>

#include <cmath>
#include <string>
#include <vector>

#include "docseek/query_parser.h"
#include "docseek/passage_ranker.h"

namespace docseek {
namespace {

// 0.25 == kCompoundPhraseBonus（产品常量，测试侧硬编码）。

TEST(QueryUnderstandingV020, ResegmentMergesDirectionTimeQuery) {
    ParsedQuery pq = parseNaturalQuery("上台前紧张，怎么用呼吸让自己稳下来？");
    EXPECT_EQ(pq.keywords.size(), 4);
    EXPECT_EQ(pq.keywords[0], "上台");
    EXPECT_EQ(pq.keywords[1], "紧张");
    EXPECT_EQ(pq.keywords[2], "呼吸");
    EXPECT_EQ(pq.keywords[3], "稳");
}

TEST(QueryUnderstandingV020, ResegmentKeepsTrueLocationWord) {
    ParsedQuery pq = parseNaturalQuery("站在台前拍照发朋友圈");
    bool has_taqian = false;
    for (const auto& k : pq.keywords) {
        if (k == "台前") {
            has_taqian = true;
            break;
        }
    }
    EXPECT_TRUE(has_taqian); // "在"+"台"不是词典词，不触发重切
}

TEST(QueryUnderstandingV020, ResegmentNoOpOnNormalQuery) {
    ParsedQuery pq = parseNaturalQuery("打印机驱动怎么安装");
    EXPECT_FALSE(pq.keywords.empty());
}

TEST(QueryUnderstandingV020, ReconstructedCompoundCollected) {
    ParsedQuery pq = parseNaturalQuery("上台前紧张，怎么用呼吸让自己稳下来？");
    EXPECT_EQ(pq.reconstructedCompounds.size(), 1u);
    EXPECT_EQ(pq.reconstructedCompounds[0], "上台紧张");
}

TEST(QueryUnderstandingV020, ReconstructedCompoundDrivesBonus) {
    ParsedQuery pq1;
    pq1.keywords = {"安装", "步骤", "说明"};
    pq1.reconstructedCompounds = {"安装步骤"};

    ParsedQuery pq2;
    pq2.keywords = {"安装", "步骤", "说明"};
    pq2.reconstructedCompounds = {};

    const std::string base = "本文介绍安装方法，步骤清晰，说明另附。";
    const std::string withBigram = "本文介绍安装步骤，说明另附。";

    // 0.25 == kCompoundPhraseBonus
    EXPECT_DOUBLE_EQ(
        rankPassages(2, "p", withBigram, pq1, 5)[0].score -
            rankPassages(1, "p", base, pq1, 5)[0].score,
        0.25);
    EXPECT_LT(
        std::fabs(rankPassages(4, "p", withBigram, pq2, 5)[0].score -
                  rankPassages(3, "p", base, pq2, 5)[0].score),
        1e-9);
}

TEST(QueryUnderstandingV020, CompoundEmptyWhenSingleKeyword) {
    ParsedQuery pq;
    pq.keywords = {"安装"};

    const std::string text = "本文介绍安装步骤。";
    double score1 = rankPassages(1, "p", text, pq, 5)[0].score;
    double score2 = rankPassages(1, "p", text, pq, 5)[0].score;
    EXPECT_DOUBLE_EQ(score1, score2);
}

TEST(QueryUnderstandingV020, EndToEndTargetQueryRanking) {
    ParsedQuery pq = parseNaturalQuery("上台前紧张，怎么用呼吸让自己稳下来？");

    const std::string good =
        "上台紧张时可以用呼吸调整，让自己稳下来，多练几次就好。";
    const std::string bad =
        "上台需要准备，紧张是常见反应，呼吸与稳都是关键词但无连续结构。";

    double goodScore = rankPassages(1, "p1", good, pq, 5)[0].score;
    double badScore = rankPassages(2, "p2", bad, pq, 5)[0].score;
    EXPECT_GT(goodScore, badScore);
}

}  // namespace
}  // namespace docseek
