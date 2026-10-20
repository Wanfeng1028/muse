#include <gtest/gtest.h>

#include <cmath>
#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

fs::path makeUniqueDir(const std::string& name) {
    fs::path dir = fs::current_path() / "test-tmp" / name;
    fs::remove_all(dir);
    fs::create_directories(dir);
    return dir;
}

void seedThreeDocs(docseek::Database& db, const fs::path& dir) {
    db.upsert((dir / "a.md").string(), "全文检索入门",
              "本文介绍全文检索的基本概念与全文检索系统的组成。", 1000, 100);
    db.upsert((dir / "b.md").string(), "数据库索引技术",
              "全文检索依赖倒排索引，全文检索性能取决于索引结构。", 2000, 200);
    db.upsert((dir / "c.md").string(), "搜索排序算法",
              "排序算法决定了搜索结果质量，与全文检索密切相关。", 3000, 300);
}

}  // namespace

TEST(HybridExplainR2, ScoreBreakdownSumMatchesFinalScore) {
    fs::path dir = makeUniqueDir("hybrid_explain_r2_sum");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    seedThreeDocs(db, dir);

    docseek::Searcher searcher(db);
    std::vector<docseek::ExplainedHit> hits = searcher.explain("全文检索", 10);

    for (const auto& eh : hits) {
        double sum = eh.breakdown.baseBm25 + eh.breakdown.titleBonus +
                     eh.breakdown.phraseBonus + eh.breakdown.structuralBonus;
        EXPECT_NEAR(eh.breakdown.finalScore, sum, 1e-6);
    }
}

TEST(HybridExplainR2, ExplainOrderMatchesSearchOrder) {
    fs::path dir = makeUniqueDir("hybrid_explain_r2_order");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    seedThreeDocs(db, dir);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> searchHits = searcher.search("全文检索", 10);
    std::vector<docseek::ExplainedHit> explainHits = searcher.explain("全文检索", 10);

    ASSERT_EQ(searchHits.size(), explainHits.size());
    for (std::size_t i = 0; i < searchHits.size(); ++i) {
        EXPECT_EQ(searchHits[i].path, explainHits[i].hit.path);
    }
}

TEST(HybridExplainR2, ExplainEmptyForNoMatchQuery) {
    fs::path dir = makeUniqueDir("hybrid_explain_r2_empty");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    seedThreeDocs(db, dir);

    docseek::Searcher searcher(db);
    std::vector<docseek::ExplainedHit> hits =
        searcher.explain("zzzz_nonexistent_token_qqqq", 10);

    EXPECT_TRUE(hits.empty());
}

TEST(HybridExplainR2, AllBreakdownComponentsNonNegative) {
    fs::path dir = makeUniqueDir("hybrid_explain_r2_nonneg");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    seedThreeDocs(db, dir);

    docseek::Searcher searcher(db);
    std::vector<docseek::ExplainedHit> hits = searcher.explain("全文检索", 10);

    for (const auto& eh : hits) {
        EXPECT_GE(eh.breakdown.baseBm25, 0.0);
        EXPECT_GE(eh.breakdown.titleBonus, 0.0);
        EXPECT_GE(eh.breakdown.phraseBonus, 0.0);
        EXPECT_GE(eh.breakdown.structuralBonus, 0.0);
        EXPECT_GE(eh.breakdown.finalScore, 0.0);
    }
}