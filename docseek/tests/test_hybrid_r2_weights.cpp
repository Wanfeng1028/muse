#include <gtest/gtest.h>

#include <filesystem>
#include <string>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

fs::path makeTempDir(const std::string& name) {
    fs::path dir = fs::current_path() / "test-tmp" / name;
    fs::remove_all(dir);
    fs::create_directories(dir);
    return dir;
}

}  // namespace

TEST(HybridWeightsR2, DefaultWeights) {
    fs::path dir = makeTempDir("hybrid_r2_default");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    docseek::Searcher s(db);
    EXPECT_DOUBLE_EQ(s.weights().titleBoost, 1.0);
    EXPECT_DOUBLE_EQ(s.weights().phraseBoost, 2.0);
}

TEST(HybridWeightsR2, ConstructWithWeights) {
    fs::path dir = makeTempDir("hybrid_r2_construct");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    docseek::SearchWeights w;
    w.titleBoost = 3.0;
    w.phraseBoost = 5.0;
    docseek::Searcher s(db, w);
    EXPECT_DOUBLE_EQ(s.weights().titleBoost, 3.0);
    EXPECT_DOUBLE_EQ(s.weights().phraseBoost, 5.0);
}

TEST(HybridWeightsR2, SetWeights) {
    fs::path dir = makeTempDir("hybrid_r2_set");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    docseek::Searcher s(db);
    docseek::SearchWeights w;
    w.titleBoost = 4.5;
    w.phraseBoost = 7.25;
    s.setWeights(w);
    EXPECT_DOUBLE_EQ(s.weights().titleBoost, 4.5);
    EXPECT_DOUBLE_EQ(s.weights().phraseBoost, 7.25);
}

TEST(HybridWeightsR2, WeightsAffectRanking) {
    fs::path dir = makeTempDir("hybrid_r2_affect");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    db.upsert((dir / "docA.txt").string(), "全文检索", "无关内容正文", 100, 10);
    db.upsert((dir / "docB.txt").string(), "普通标题", "全文检索出现在正文里", 100, 10);

    docseek::Searcher s(db);
    std::vector<docseek::Hit> hits = s.search("全文检索", 10);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits.front().title, "全文检索");

    docseek::SearchWeights w;
    w.titleBoost = 0.0;
    w.phraseBoost = 2.0;
    s.setWeights(w);
    std::vector<docseek::Hit> hits2 = s.search("全文检索", 10);
    ASSERT_GE(hits2.size(), static_cast<size_t>(2));

    bool foundA = false;
    bool foundB = false;
    for (const auto& h : hits2) {
        if (h.title == "全文检索") foundA = true;
        if (h.title == "普通标题") foundB = true;
    }
    EXPECT_TRUE(foundA);
    EXPECT_TRUE(foundB);
}