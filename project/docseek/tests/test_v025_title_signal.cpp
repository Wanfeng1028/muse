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

// title 命中 2 个关键词 -> 文档级加成 0.2；正文无命中时窗口 base=0.05。
TEST(TitleSignal, TitleKeywordBonus) {
    ParsedQuery pq = makePq({"无人机", "电池"});
    TermWeights w = makeWeights({{"无人机", 1.0}, {"电池", 1.0}});
    std::string content = "甲行\n乙行\n丙行";
    auto withTitle = rankPassages(1, "t.txt", content, pq, 10, w, "无人机电池保养的几条土办法");
    auto noTitle = rankPassages(1, "t.txt", content, pq, 10, w, "");
    ASSERT_EQ(withTitle.size(), 1u);
    ASSERT_EQ(noTitle.size(), 1u);
    EXPECT_DOUBLE_EQ(withTitle[0].score, 0.05 + 0.17);
    EXPECT_DOUBLE_EQ(noTitle[0].score, 0.05);
    EXPECT_NEAR(withTitle[0].score - noTitle[0].score, 0.17, 1e-9);
}

// title 为空时 content 首行 markdown 标题提供标题信号；第 2 个窗口（line_start==4）
// 正文无命中，分数 = 0.05*(1/1.1) + 0.17。
TEST(TitleSignal, HeadingFallback) {
    ParsedQuery pq = makePq({"无人机", "电池"});
    TermWeights w = makeWeights({{"无人机", 1.0}, {"电池", 1.0}});
    std::string content = "# 无人机电池保养\n甲行\n乙行\n丙行\n丁行\n戊行\n己行\n庚行";
    auto r = rankPassages(1, "t.md", content, pq, 10, w, "");
    ASSERT_GE(r.size(), 2u);
    ASSERT_EQ(r[1].line_start, 4);
    EXPECT_DOUBLE_EQ(r[1].score, 0.05 * (1.0 / (1.0 + 0.1)) + 0.17);
}

// 去重语义：同一词在 title 与首行标题同时命中只计一次。
// A(title="无人机电池保养")+首行标题含"无人机/电池" -> 并集{无人机,电池}=0.2；
// B(无 title)+同首行标题 -> 0.2；两组窗口文本完全相同故 base 一致，差值 0 证明未双重计分
// （若无去重，A 应为 0.4，差值 0.2）。
TEST(TitleSignal, NoDoubleCount) {
    ParsedQuery pq = makePq({"无人机", "电池"});
    TermWeights w = makeWeights({{"无人机", 1.0}, {"电池", 1.0}});
    std::string content = "# 无人机电池保养\n甲行\n乙行";
    auto a = rankPassages(1, "t.md", content, pq, 10, w, "无人机电池保养");
    auto b = rankPassages(1, "t.md", content, pq, 10, w, "");
    ASSERT_EQ(a.size(), b.size());
    ASSERT_GT(a.size(), 0u);
    EXPECT_NEAR(a[0].score - b[0].score, 0.0, 1e-9);
}

// 标题加成只按词长权重缩放、无视传入的 idf 权重：
// "无人机"三字 -> 1.0，"电池"双字 -> 0.7，加成 = 0.1*1.0 + 0.1*0.7 = 0.17；
// 纵使传入 weights {"无人机":2.0,"电池":0.5} 也分毫不差（正文无命中故 weights 不影响 base）。
TEST(TitleSignal, WeightIgnoresIdfWeights) {
    ParsedQuery pq = makePq({"无人机", "电池"});
    TermWeights w = makeWeights({{"无人机", 2.0}, {"电池", 0.5}});
    std::string content = "甲行\n乙行\n丙行";
    auto r = rankPassages(1, "t.txt", content, pq, 10, w, "无人机电池保养");
    ASSERT_EQ(r.size(), 1u);
    EXPECT_DOUBLE_EQ(r[0].score, 0.05 + 0.17);
    // 单字词降权对照："充"单字 -> 0.35，加成 0.035。
    ParsedQuery pq2 = makePq({"充"});
    auto r2 = rankPassages(1, "t.txt", content, pq2, 10, w, "充电宝选购");
    ASSERT_EQ(r2.size(), 1u);
    EXPECT_DOUBLE_EQ(r2[0].score, 0.05 + 0.035);
}

// title 与关键词无交集 -> 加成 0，分数与无 title 逐位相同。
TEST(TitleSignal, NoMatchNoBonus) {
    ParsedQuery pq = makePq({"无人机", "电池"});
    TermWeights w = makeWeights({{"无人机", 1.0}, {"电池", 1.0}});
    std::string content = "甲行\n乙行\n丙行";
    auto a = rankPassages(1, "t.txt", content, pq, 10, w, "煲汤食谱大全");
    auto b = rankPassages(1, "t.txt", content, pq, 10, w, "");
    ASSERT_EQ(a.size(), b.size());
    for (size_t i = 0; i < a.size(); ++i) {
        EXPECT_DOUBLE_EQ(a[i].score, b[i].score);
    }
}

// 6 参数重载 == 7 参数传空 title：分数逐位相同（老调用方行为不变）。
TEST(TitleSignal, BackwardCompat) {
    ParsedQuery pq = makePq({"无人机", "电池"});
    TermWeights w = makeWeights({{"无人机", 1.0}, {"电池", 1.0}});
    std::string content = "# 无人机电池保养\n甲行\n电池长期存放\n丙行";
    auto a = rankPassages(1, "t.md", content, pq, 10, w);
    auto b = rankPassages(1, "t.md", content, pq, 10, w, "");
    ASSERT_EQ(a.size(), b.size());
    for (size_t i = 0; i < a.size(); ++i) {
        EXPECT_DOUBLE_EQ(a[i].score, b[i].score);
    }
}
