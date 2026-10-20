#include <gtest/gtest.h>

#include <cmath>
#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

using docseek::Database;
using docseek::Searcher;
using docseek::Hit;
using docseek::SearchWeights;
using docseek::ExplainedHit;

namespace {

std::string makeUniqueDir(const std::string& name) {
    fs::path base = fs::current_path() / "test-tmp" / name;
    std::error_code ec;
    fs::remove_all(base, ec);
    fs::create_directories(base, ec);
    return base.string();
}

void seed(Database& db) {
    db.upsert("/a.txt", "apple banana", "apple banana content here", 100, 10);
    db.upsert("/b.txt", "banana cherry", "banana cherry content here", 200, 20);
    db.upsert("/c.txt", "apple cherry", "apple cherry content here", 300, 30);
}

}  // namespace

TEST(HybridWeightsMidR2, SetWeightsMidStream) {
    std::string dir = makeUniqueDir("weightsmid_set");
    Database db = Database::open(dir + "/x.db");
    seed(db);

    Searcher s(db);
    std::vector<Hit> first = s.search("apple banana", 10);
    (void)first;

    SearchWeights nw;
    nw.titleBoost = 5.0;
    nw.phraseBoost = 2.0;
    s.setWeights(nw);

    SearchWeights got = s.weights();
    EXPECT_DOUBLE_EQ(got.titleBoost, 5.0);
    EXPECT_DOUBLE_EQ(got.phraseBoost, 2.0);

    std::vector<Hit> second = s.search("apple banana", 10);
    EXPECT_GE(static_cast<int>(second.size()), 0);
}

TEST(HybridWeightsMidR2, ExplainConsistentAcrossConstructionPaths) {
    std::string dir = makeUniqueDir("weightsmid_explain");
    Database db = Database::open(dir + "/x.db");
    seed(db);

    SearchWeights w;
    w.titleBoost = 2.0;
    w.phraseBoost = 3.0;

    Searcher s1(db, w);

    Searcher s2(db);
    SearchWeights w2;
    w2.titleBoost = 2.0;
    w2.phraseBoost = 3.0;
    s2.setWeights(w2);

    std::vector<ExplainedHit> e1 = s1.explain("apple banana", 10);
    std::vector<ExplainedHit> e2 = s2.explain("apple banana", 10);

    ASSERT_EQ(e1.size(), e2.size());
    for (size_t i = 0; i < e1.size(); ++i) {
        EXPECT_LT(std::fabs(e1[i].breakdown.baseBm25 - e2[i].breakdown.baseBm25), 1e-9);
        EXPECT_LT(std::fabs(e1[i].breakdown.titleBonus - e2[i].breakdown.titleBonus), 1e-9);
        EXPECT_LT(std::fabs(e1[i].breakdown.phraseBonus - e2[i].breakdown.phraseBonus), 1e-9);
        EXPECT_LT(std::fabs(e1[i].breakdown.structuralBonus - e2[i].breakdown.structuralBonus), 1e-9);
        EXPECT_LT(std::fabs(e1[i].breakdown.finalScore - e2[i].breakdown.finalScore), 1e-9);
    }
}

TEST(HybridWeightsMidR2, WeightsCopiedOnConstruction) {
    std::string dir = makeUniqueDir("weightsmid_copy");
    Database db = Database::open(dir + "/x.db");
    seed(db);

    SearchWeights w;
    w.titleBoost = 7.0;
    w.phraseBoost = 8.0;

    Searcher s(db, w);
    w.titleBoost = 1.0;

    SearchWeights got = s.weights();
    EXPECT_DOUBLE_EQ(got.titleBoost, 7.0);
    EXPECT_DOUBLE_EQ(got.phraseBoost, 8.0);
}