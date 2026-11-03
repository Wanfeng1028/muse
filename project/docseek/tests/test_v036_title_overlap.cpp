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

// 关键词按字节长度降序认领，"温度控制"最长先认领，"温度""控制"重叠不再计分。
// 仅"温度控制"计分 0.1*1.0=0.1，加上窗口 base 0.05 = 0.15。
TEST(TitleOverlap, CompoundClaimsLongestOnly) {
    ParsedQuery pq = makePq({"热敷", "眼睛", "温度", "控制", "温度控制"});
    TermWeights w = makeWeights({{"热敷", 1.0}, {"眼睛", 1.0}, {"温度", 1.0}, {"控制", 1.0}, {"温度控制", 1.0}});
    std::string content = "甲行\n乙行\n丙行";
    auto r = rankPassages(1, "t.txt", content, pq, 10, w, "奶泡温度控制");
    ASSERT_EQ(r.size(), 1u);
    EXPECT_DOUBLE_EQ(r[0].score, 0.05 + 0.10);
}

// "温度""控制"不重叠，各计分 0.1*0.7=0.07，加上 base 0.05 = 0.19。
TEST(TitleOverlap, NonOverlappingBothCount) {
    ParsedQuery pq = makePq({"温度", "控制"});
    TermWeights w = makeWeights({{"温度", 1.0}, {"控制", 1.0}});
    std::string content = "甲行\n乙行\n丙行";
    auto r = rankPassages(1, "t.txt", content, pq, 10, w, "温度高，控制好");
    ASSERT_EQ(r.size(), 1u);
    EXPECT_DOUBLE_EQ(r[0].score, 0.05 + 0.07 + 0.07);
}

// "温度控制"先认领前四个字，"温度"再认领后出现的"温度"（不重叠），各计一次。
// 0.1*1.0 + 0.1*0.7 = 0.17，加上 base 0.05 = 0.22。
TEST(TitleOverlap, FreeOccurrenceElsewhereCounts) {
    ParsedQuery pq = makePq({"温度", "温度控制"});
    TermWeights w = makeWeights({{"温度", 1.0}, {"温度控制", 1.0}});
    std::string content = "甲行\n乙行\n丙行";
    auto r = rankPassages(1, "t.txt", content, pq, 10, w, "温度控制，温度要稳");
    ASSERT_EQ(r.size(), 1u);
    EXPECT_DOUBLE_EQ(r[0].score, 0.05 + 0.10 + 0.07);
}

// 首行标题 "# 温度控制指南" 充当标题，"温度控制"认领后"温度""控制"重叠不计。
// 第二窗口 line_start==4，base = 0.05/(1+0.1*1)，标题加成 0.1*1.0=0.1。
TEST(TitleOverlap, HeadingOverlapDedup) {
    ParsedQuery pq = makePq({"温度", "控制", "温度控制"});
    TermWeights w = makeWeights({{"温度", 1.0}, {"控制", 1.0}, {"温度控制", 1.0}});
    std::string content = "# 温度控制指南\n甲行\n乙行\n丙行\n丁行\n戊行\n己行\n庚行";
    auto r = rankPassages(1, "t.md", content, pq, 10, w, "");
    ASSERT_GE(r.size(), 2u);
    ASSERT_EQ(r[1].line_start, 4);
    EXPECT_DOUBLE_EQ(r[1].score, 0.05 * (1.0 / (1.0 + 0.1)) + 0.10);
}

// "篆书"双字计 0.07，"写"单字计 0.035，两者在标题中位置不重叠，各计一次。
// 加上 base 0.05 = 0.155。
TEST(TitleOverlap, SingleCharNotSwallowed) {
    ParsedQuery pq = makePq({"写", "篆书"});
    TermWeights w = makeWeights({{"写", 1.0}, {"篆书", 1.0}});
    std::string content = "甲行\n乙行\n丙行";
    auto r = rankPassages(1, "t.txt", content, pq, 10, w, "写篆书");
    ASSERT_EQ(r.size(), 1u);
    EXPECT_DOUBLE_EQ(r[0].score, 0.05 + 0.035 + 0.07);
}