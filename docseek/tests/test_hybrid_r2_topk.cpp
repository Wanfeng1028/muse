#include <gtest/gtest.h>

#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

struct Fixture {
    fs::path dir;
    docseek::Database db;
};

Fixture makeFixture(const std::string& name) {
    fs::path dir = fs::current_path() / "test-tmp" / name;
    fs::remove_all(dir);
    fs::create_directories(dir);
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    return Fixture{dir, std::move(db)};
}

void seed(docseek::Database& db) {
    db.upsert("a.md", "全文检索指南", "全文检索的基本用法与全文检索示例", 100, 10);
    db.upsert("b.md", "普通标题", "这里讨论全文检索的实现细节，全文检索很重要", 101, 20);
    db.upsert("c.md", "全文检索进阶", "深入理解全文检索", 102, 30);
    db.upsert("d.md", "文档", "全文检索与全文检索的性能对比全文检索", 103, 40);
    db.upsert("e.md", "全文检索总结", "总结全文检索的要点", 104, 50);
}

}  // namespace

TEST(HybridTopKR2, LimitOneReturnsSingleHit) {
    Fixture f = makeFixture("hybrid_r2_topk_limit1");
    seed(f.db);
    docseek::Searcher searcher(f.db);
    std::vector<docseek::Hit> hits = searcher.search("全文检索", 1);
    EXPECT_EQ(hits.size(), 1u);
}

TEST(HybridTopKR2, LimitHundredReturnsAllFive) {
    Fixture f = makeFixture("hybrid_r2_topk_limit100");
    seed(f.db);
    docseek::Searcher searcher(f.db);
    std::vector<docseek::Hit> hits = searcher.search("全文检索", 100);
    EXPECT_EQ(hits.size(), 5u);
}

TEST(HybridTopKR2, ScoresAreNonIncreasing) {
    Fixture f = makeFixture("hybrid_r2_topk_scores");
    seed(f.db);
    docseek::Searcher searcher(f.db);
    std::vector<docseek::Hit> hits = searcher.search("全文检索", 100);
    for (size_t i = 0; i + 1 < hits.size(); ++i) {
        EXPECT_GE(hits[i].score, hits[i + 1].score);
    }
}

TEST(HybridTopKR2, ExplainFinalScoreMatchesHitScore) {
    Fixture f = makeFixture("hybrid_r2_topk_explain");
    seed(f.db);
    docseek::Searcher searcher(f.db);
    std::vector<docseek::ExplainedHit> explained = searcher.explain("全文检索", 3);
    EXPECT_EQ(explained.size(), 3u);
    for (const auto& e : explained) {
        EXPECT_LT(std::abs(e.breakdown.finalScore - e.hit.score), 1e-6);
    }
}

TEST(HybridTopKR2, LimitTwoPrefixMatchesLimitHundredPrefix) {
    Fixture f = makeFixture("hybrid_r2_topk_prefix");
    seed(f.db);
    docseek::Searcher searcher(f.db);
    std::vector<docseek::Hit> small = searcher.search("全文检索", 2);
    std::vector<docseek::Hit> large = searcher.search("全文检索", 100);
    ASSERT_GE(large.size(), 2u);
    ASSERT_EQ(small.size(), 2u);
    EXPECT_EQ(small[0].path, large[0].path);
    EXPECT_EQ(small[1].path, large[1].path);
}