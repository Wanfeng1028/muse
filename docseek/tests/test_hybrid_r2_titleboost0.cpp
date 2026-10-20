#include <gtest/gtest.h>

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

void seedDocs(docseek::Database& db) {
    db.upsert("/docs/a.txt", "全文检索指南", "aaa", 100, 3);
    db.upsert("/docs/b.txt", "其他", "全文检索指南bbb", 100, 12);
}

}  // namespace

TEST(HybridTitleBoost0R2, DefaultWeightTitleBoostRanksAFirst) {
    fs::path dir = makeUniqueDir("hybrid_r2_tb0_default_rank");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    seedDocs(db);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("全文检索", 10);

    ASSERT_GE(hits.size(), 2u);
    EXPECT_EQ(hits[0].path, "/docs/a.txt");
    EXPECT_EQ(hits[1].path, "/docs/b.txt");
}

TEST(HybridTitleBoost0R2, ExplainDefaultTitleBonusAExceedsB) {
    fs::path dir = makeUniqueDir("hybrid_r2_tb0_explain_default");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    seedDocs(db);

    docseek::Searcher searcher(db);
    std::vector<docseek::ExplainedHit> explained = searcher.explain("全文检索", 10);

    ASSERT_GE(explained.size(), 2u);
    double titleBonusA = -1.0;
    double titleBonusB = -1.0;
    for (const auto& eh : explained) {
        if (eh.hit.path == "/docs/a.txt") {
            titleBonusA = eh.breakdown.titleBonus;
        } else if (eh.hit.path == "/docs/b.txt") {
            titleBonusB = eh.breakdown.titleBonus;
        }
    }
    ASSERT_GE(titleBonusA, 0.0);
    ASSERT_GE(titleBonusB, 0.0);
    EXPECT_GT(titleBonusA, titleBonusB);
}

TEST(HybridTitleBoost0R2, ZeroTitleBoostEliminatesTitleBonus) {
    fs::path dir = makeUniqueDir("hybrid_r2_tb0_zero_boost");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    seedDocs(db);

    docseek::Searcher searcher(db);
    docseek::SearchWeights weights;
    weights.titleBoost = 0.0;
    weights.phraseBoost = 2.0;
    searcher.setWeights(weights);

    std::vector<docseek::ExplainedHit> explained = searcher.explain("全文检索", 10);

    ASSERT_GE(explained.size(), 2u);
    bool sawA = false;
    bool sawB = false;
    for (const auto& eh : explained) {
        if (eh.hit.path == "/docs/a.txt") {
            sawA = true;
            EXPECT_DOUBLE_EQ(eh.breakdown.titleBonus, 0.0);
        } else if (eh.hit.path == "/docs/b.txt") {
            sawB = true;
            EXPECT_DOUBLE_EQ(eh.breakdown.titleBonus, 0.0);
        }
    }
    EXPECT_TRUE(sawA);
    EXPECT_TRUE(sawB);
}