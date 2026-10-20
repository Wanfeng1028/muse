#include <gtest/gtest.h>
#include "docseek/passage_ranker.h"
#include "docseek/query_parser.h"
#include <string>
#include <vector>
#include <unordered_map>
#include <cmath>

using namespace docseek;

TEST(WeightedPassage, TermLengthWeight_SingleChar) {
    EXPECT_DOUBLE_EQ(termLengthWeight("算"), 0.35);
}

TEST(WeightedPassage, TermLengthWeight_TwoChars) {
    EXPECT_DOUBLE_EQ(termLengthWeight("备份"), 0.7);
}

TEST(WeightedPassage, TermLengthWeight_ThreePlus) {
    EXPECT_DOUBLE_EQ(termLengthWeight("备份数据"), 1.0);
    EXPECT_DOUBLE_EQ(termLengthWeight("backup"), 1.0);
}

TEST(WeightedPassage, TermLengthWeight_Empty) {
    EXPECT_DOUBLE_EQ(termLengthWeight(""), 0.35);
}

TEST(WeightedPassage, UniformWeights_IdenticalScores) {
    ParsedQuery pq;
    pq.keywords = {"备份", "数据", "建议"};
    std::string content = "第一行包含备份\n第二行包含数据\n第三行包含建议";
    TermWeights weights;
    weights.weights["备份"] = 1.0;
    weights.weights["数据"] = 1.0;
    weights.weights["建议"] = 1.0;
    
    auto result5 = rankPassages(1, "test.txt", content, pq, 10);
    auto result6 = rankPassages(1, "test.txt", content, pq, 10, weights);
    
    ASSERT_EQ(result5.size(), result6.size());
    for (size_t i = 0; i < result5.size(); ++i) {
        EXPECT_DOUBLE_EQ(result5[i].score, result6[i].score);
    }
}

TEST(WeightedPassage, MissingWeight_DefaultsToOne) {
    ParsedQuery pq;
    pq.keywords = {"备份", "数据"};
    std::string content = "第一行包含备份\n第二行包含数据";
    TermWeights empty_weights;
    
    auto result5 = rankPassages(1, "test.txt", content, pq, 10);
    auto result6 = rankPassages(1, "test.txt", content, pq, 10, empty_weights);
    
    ASSERT_EQ(result5.size(), result6.size());
    for (size_t i = 0; i < result5.size(); ++i) {
        EXPECT_DOUBLE_EQ(result5[i].score, result6[i].score);
    }
}

TEST(WeightedPassage, SingleCharNoise_Suppressed) {
    ParsedQuery pq;
    pq.keywords = {"备份", "算", "能", "点"};
    std::string content = 
        "算能点算能点算能点\n"
        "算能点算能点算能点\n"
        "算能点算能点算能点\n"
        "备份";
    TermWeights weights;
    weights.weights["备份"] = 2.0;
    weights.weights["算"] = 0.2;
    weights.weights["能"] = 0.2;
    weights.weights["点"] = 0.2;
    
    auto result = rankPassages(1, "test.txt", content, pq, 10, weights);
    ASSERT_FALSE(result.empty());
    EXPECT_NE(result[0].text.find("备份"), std::string::npos);
}

TEST(WeightedPassage, HighFreqTerm_Downweighted) {
    ParsedQuery pq;
    pq.keywords = {"备份", "建议"};
    std::string content = 
        "建议建议建议建议建议\n"
        "备份备份";
    TermWeights weights;
    weights.weights["备份"] = 1.5;
    weights.weights["建议"] = 0.3;
    
    auto result = rankPassages(1, "test.txt", content, pq, 10, weights);
    ASSERT_FALSE(result.empty());
    EXPECT_NE(result[0].text.find("备份"), std::string::npos);
}

TEST(WeightedPassage, ZeroWeightTerm_Excluded) {
    ParsedQuery pq;
    pq.keywords = {"备份", "忽略"};
    std::string content = "备份 忽略";
    TermWeights weights;
    weights.weights["忽略"] = 0.0;
    weights.weights["备份"] = 1.0;
    
    auto result = rankPassages(1, "test.txt", content, pq, 10, weights);
    ASSERT_FALSE(result.empty());
    bool found = false;
    for (const auto& term : result[0].matched_terms) {
        if (term == "备份") {
            found = true;
            break;
        }
    }
    EXPECT_TRUE(found);
    EXPECT_GT(result[0].score, 0.0);
}

TEST(WeightedPassage, PhraseWeight_NotWeighted_ByDesign) {
    ParsedQuery pq;
    pq.keywords = {"备份"};
    pq.phrases = {"数据备份"};
    std::string content = "数据备份";
    TermWeights w1;
    w1.weights["备份"] = 1.0;
    w1.weights["数据备份"] = 2.0;
    TermWeights w2;
    w2.weights["备份"] = 1.0;
    w2.weights["数据备份"] = 0.1;
    auto r1 = rankPassages(1, "t.txt", content, pq, 10, w1);
    auto r2 = rankPassages(1, "t.txt", content, pq, 10, w2);
    ASSERT_FALSE(r1.empty());
    ASSERT_FALSE(r2.empty());
    EXPECT_DOUBLE_EQ(r1[0].score, r2[0].score);
}

TEST(WeightedPassage, EmptyContent_EmptyResult) {
    ParsedQuery pq;
    pq.keywords = {"备份"};
    std::string content = "";
    TermWeights weights;
    weights.weights["备份"] = 1.0;
    
    auto result = rankPassages(1, "test.txt", content, pq, 10, weights);
    EXPECT_TRUE(result.empty());
}

TEST(WeightedPassage, TopKZero_EmptyResult) {
    ParsedQuery pq;
    pq.keywords = {"备份"};
    std::string content = "备份";
    TermWeights weights;
    weights.weights["备份"] = 1.0;
    
    auto result = rankPassages(1, "test.txt", content, pq, 0, weights);
    EXPECT_TRUE(result.empty());
}
