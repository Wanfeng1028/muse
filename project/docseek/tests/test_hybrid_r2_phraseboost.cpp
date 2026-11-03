#include <gtest/gtest.h>

#include <filesystem>
#include <string>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

fs::path makeUniqueDir(const std::string& name) {
    fs::path base = fs::current_path() / "test-tmp" / name;
    std::error_code ec;
    fs::remove_all(base, ec);
    fs::create_directories(base, ec);
    return base;
}

void seedDocs(docseek::Database& db, const fs::path& dir) {
    db.upsert((dir / "docA.txt").string(), "其他", "全文检索是一门技术", 1000, 100);
    db.upsert((dir / "docB.txt").string(), "其他", "全文的检索技术很复杂", 1000, 100);
}

}  // namespace

TEST(HybridPhraseBoostR2, BothDocsReturnedForAndQuery) {
    fs::path dir = makeUniqueDir("hybrid_phrase_r2_both");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    seedDocs(db, dir);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("全文 检索", 10);

    bool foundA = false;
    bool foundB = false;
    for (const auto& h : hits) {
        if (h.path == (dir / "docA.txt").string()) foundA = true;
        if (h.path == (dir / "docB.txt").string()) foundB = true;
    }
    EXPECT_TRUE(foundA);
    EXPECT_TRUE(foundB);
}

TEST(HybridPhraseBoostR2, PhraseBonusDefaultWeights) {
    fs::path dir = makeUniqueDir("hybrid_phrase_r2_default");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    seedDocs(db, dir);

    docseek::Searcher searcher(db);
    std::vector<docseek::ExplainedHit> explained = searcher.explain("全文 检索", 10);

    bool foundA = false;
    bool foundB = false;
    for (const auto& eh : explained) {
        if (eh.hit.path == (dir / "docA.txt").string()) {
            foundA = true;
            EXPECT_NEAR(eh.breakdown.phraseBonus, 2.0, 1e-9);
        }
        if (eh.hit.path == (dir / "docB.txt").string()) {
            foundB = true;
            EXPECT_NEAR(eh.breakdown.phraseBonus, 0.0, 1e-9);
        }
    }
    EXPECT_TRUE(foundA);
    EXPECT_TRUE(foundB);
}

TEST(HybridPhraseBoostR2, PhraseBonusZeroWhenWeightZero) {
    fs::path dir = makeUniqueDir("hybrid_phrase_r2_zero");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    seedDocs(db, dir);

    docseek::Searcher searcher(db);
    docseek::SearchWeights w;
    w.titleBoost = 1.0;
    w.phraseBoost = 0.0;
    searcher.setWeights(w);

    std::vector<docseek::ExplainedHit> explained = searcher.explain("全文 检索", 10);

    bool foundA = false;
    bool foundB = false;
    for (const auto& eh : explained) {
        if (eh.hit.path == (dir / "docA.txt").string()) {
            foundA = true;
            EXPECT_NEAR(eh.breakdown.phraseBonus, 0.0, 1e-9);
        }
        if (eh.hit.path == (dir / "docB.txt").string()) {
            foundB = true;
            EXPECT_NEAR(eh.breakdown.phraseBonus, 0.0, 1e-9);
        }
    }
    EXPECT_TRUE(foundA);
    EXPECT_TRUE(foundB);
}

TEST(HybridPhraseBoostR2, HighPhraseBoostRanksDocAFirst) {
    fs::path dir = makeUniqueDir("hybrid_phrase_r2_high");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    seedDocs(db, dir);

    docseek::Searcher searcher(db);
    docseek::SearchWeights w;
    w.titleBoost = 1.0;
    w.phraseBoost = 100.0;
    searcher.setWeights(w);

    std::vector<docseek::Hit> hits = searcher.search("全文 检索", 10);

    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits.front().path, (dir / "docA.txt").string());
}
