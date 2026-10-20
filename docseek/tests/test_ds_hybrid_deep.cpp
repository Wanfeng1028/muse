#include "docseek/database.h"
#include "docseek/searcher.h"

using namespace docseek;
#include <gtest/gtest.h>
#include <filesystem>
#include <string>
#include <vector>
#include <cmath>

namespace fs = std::filesystem;
namespace {
fs::path makeDsDir(const std::string& name) {
    fs::path base = fs::current_path() / "test-tmp" / name;
    std::error_code ec; fs::remove_all(base, ec); fs::create_directories(base, ec);
    return base;
}
}

TEST(HybridDeepDS, KeywordRecall) {
    auto dir = makeDsDir("ds_h1");
    auto db = Database::open((dir / "x.db").string());
    db.upsert("a.txt", "检索指南", "全文检索是信息检索的核心技术", 0, 0);
    db.upsert("b.txt", "天气", "今天天气很好", 0, 0);
    Searcher s(db);
    auto hits = s.search("全文检索", 10);
    EXPECT_FALSE(hits.empty());
    EXPECT_EQ(hits.size(), 1u);
    EXPECT_NE(hits[0].path.find("a.txt"), std::string::npos);
}

TEST(HybridDeepDS, EmptyGuards) {
    auto dir = makeDsDir("ds_h2");
    auto db = Database::open((dir / "x.db").string());
    db.upsert("a.txt", "标题", "这是一篇关于检索的测试文档内容", 0, 0);
    Searcher s(db);
    EXPECT_TRUE(s.search("", 10).empty());
    EXPECT_TRUE(s.search("   ", 10).empty());
    EXPECT_TRUE(s.search("！！？？", 10).empty());
    std::string big;
    for (int i = 0; i < 3000; ++i) big += "啊";
    EXPECT_TRUE(s.search(big, 10).empty());
    EXPECT_TRUE(s.search("全文检索", 0).empty());
    EXPECT_TRUE(s.search("全文检索", -1).empty());
}

TEST(HybridDeepDS, SpecialCharsNoCrash) {
    auto dir = makeDsDir("ds_h3");
    auto db = Database::open((dir / "x.db").string());
    db.upsert("a.txt", "标题", "内容", 0, 0);
    Searcher s(db);
    EXPECT_NO_THROW(s.search("全文\"检索", 10));
    EXPECT_NO_THROW(s.search("C++", 10));
}

TEST(HybridDeepDS, TopNBoundaries) {
    auto dir = makeDsDir("ds_h4");
    auto db = Database::open((dir / "x.db").string());
    db.upsert("a.txt", "标题", "全文检索", 0, 0);
    db.upsert("b.txt", "标题", "全文检索", 0, 0);
    db.upsert("c.txt", "标题", "全文检索", 0, 0);
    Searcher s(db);
    auto h1 = s.search("全文检索", 1);
    EXPECT_EQ(h1.size(), 1u);
    auto h2 = s.search("全文检索", 2);
    EXPECT_EQ(h2.size(), 2u);
    auto h10 = s.search("全文检索", 10);
    EXPECT_EQ(h10.size(), 3u);
    EXPECT_EQ(h2[0].path, h10[0].path);
    EXPECT_EQ(h2[1].path, h10[1].path);
}

TEST(HybridDeepDS, ScoreMonotonic) {
    auto dir = makeDsDir("ds_h5");
    auto db = Database::open((dir / "x.db").string());
    db.upsert("a.txt", "标题", "全文检索", 0, 0);
    db.upsert("b.txt", "标题", "全文检索", 0, 0);
    db.upsert("c.txt", "标题", "全文检索", 0, 0);
    Searcher s(db);
    auto hits = s.search("全文检索", 10);
    for (size_t i = 1; i < hits.size(); ++i) {
        EXPECT_LE(hits[i].score, hits[i-1].score);
    }
}

TEST(HybridDeepDS, StableOrder) {
    auto dir = makeDsDir("ds_h6");
    auto db = Database::open((dir / "x.db").string());
    db.upsert("a.txt", "标题A", "相同内容", 0, 0);
    db.upsert("b.txt", "标题B", "相同内容", 0, 0);
    Searcher s(db);
    auto h1 = s.search("相同内容", 10);
    auto h2 = s.search("相同内容", 10);
    EXPECT_EQ(h1.size(), h2.size());
    for (size_t i = 0; i < h1.size() && i < h2.size(); ++i) {
        EXPECT_EQ(h1[i].path, h2[i].path);
    }
    if (h1.size() >= 2) {
        EXPECT_DOUBLE_EQ(h1[0].score, h1[1].score);
    }
}

TEST(HybridDeepDS, StopwordOnly) {
    auto dir = makeDsDir("ds_h7");
    auto db = Database::open((dir / "x.db").string());
    db.upsert("a.txt", "标题", "内容", 0, 0);
    Searcher s(db);
    EXPECT_TRUE(s.search("的", 10).empty());
}

TEST(HybridDeepDS, OrFallback) {
    auto dir = makeDsDir("ds_h8");
    auto db = Database::open((dir / "x.db").string());
    db.upsert("a.txt", "标题", "量子计算是未来方向", 0, 0);
    Searcher s(db);
    auto hits = s.search("量子计算 不存在词xyz", 10);
    EXPECT_FALSE(hits.empty());
    bool found = false;
    for (const auto& h : hits) {
        if (h.path.find("a.txt") != std::string::npos) found = true;
    }
    EXPECT_TRUE(found);
}

TEST(HybridDeepDS, NoResult) {
    auto dir = makeDsDir("ds_h9");
    auto db = Database::open((dir / "x.db").string());
    db.upsert("a.txt", "标题", "内容", 0, 0);
    Searcher s(db);
    EXPECT_TRUE(s.search("不存在的词qzxwvk", 10).empty());
}

TEST(HybridDeepDS, ExplainConsistency) {
    auto dir = makeDsDir("ds_h10");
    auto db = Database::open((dir / "x.db").string());
    db.upsert("a.txt", "检索指南", "全文检索是信息检索的核心技术", 0, 0);
    db.upsert("b.txt", "天气", "今天天气很好", 0, 0);
    Searcher s(db);
    auto ex = s.explain("全文检索", 3);
    EXPECT_FALSE(ex.empty());
    for (const auto& e : ex) {
        EXPECT_LT(std::abs(e.breakdown.finalScore - e.hit.score), 1e-6);
        double sum = e.breakdown.baseBm25 + e.breakdown.titleBonus + e.breakdown.phraseBonus + e.breakdown.structuralBonus;
        EXPECT_LT(std::abs(e.breakdown.finalScore - sum), 1e-6);
    }
    auto q = s.searchQuestion("全文检索", 10);
    EXPECT_FALSE(q.empty());
}