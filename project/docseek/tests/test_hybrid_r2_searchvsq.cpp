#include <gtest/gtest.h>

#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

std::string makeTempDir(const std::string& name) {
    fs::path base = fs::current_path() / "test-tmp" / name;
    fs::remove_all(base);
    fs::create_directories(base);
    return base.string();
}

bool containsPath(const std::vector<docseek::Hit>& hits, const std::string& path) {
    for (const auto& h : hits) {
        if (h.path == path) return true;
    }
    return false;
}

}  // namespace

TEST(HybridSearchVsQR2, SearchHitsDocBWithApplePhone) {
    std::string dir = makeTempDir("hvq_search_apple_phone");
    docseek::Database db = docseek::Database::open(dir + "/x.db");

    std::string pathA = dir + "/docA.md";
    std::string pathB = dir + "/docB.md";
    db.upsert(pathA, "手机", "苹果手机", 1, 4);
    db.upsert(pathB, "水果", "香蕉水果", 1, 4);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("苹果手机", 10);

    EXPECT_TRUE(containsPath(hits, pathB));
}

TEST(HybridSearchVsQR2, SearchQuestionUnionHitsBoth) {
    std::string dir = makeTempDir("hvq_searchq_union");
    docseek::Database db = docseek::Database::open(dir + "/x.db");

    std::string pathA = dir + "/docA.md";
    std::string pathB = dir + "/docB.md";
    db.upsert(pathA, "手机", "苹果手机", 1, 4);
    db.upsert(pathB, "水果", "香蕉水果", 1, 4);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.searchQuestion("苹果 香蕉", 10);

    EXPECT_TRUE(containsPath(hits, pathA));
    EXPECT_TRUE(containsPath(hits, pathB));
}

TEST(HybridSearchVsQR2, SearchAndSearchQuestionMayDiffer) {
    std::string dir = makeTempDir("hvq_diff");
    docseek::Database db = docseek::Database::open(dir + "/x.db");

    std::string pathA = dir + "/docA.md";
    std::string pathB = dir + "/docB.md";
    db.upsert(pathA, "手机", "苹果手机", 1, 4);
    db.upsert(pathB, "水果", "香蕉水果", 1, 4);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> sHits = searcher.search("苹果 香蕉", 10);
    std::vector<docseek::Hit> qHits = searcher.searchQuestion("苹果 香蕉", 10);

    EXPECT_LE(sHits.size(), qHits.size());
}

TEST(HybridSearchVsQR2, EmptyQueryReturnsEmpty) {
    std::string dir = makeTempDir("hvq_empty");
    docseek::Database db = docseek::Database::open(dir + "/x.db");

    std::string pathA = dir + "/docA.md";
    std::string pathB = dir + "/docB.md";
    db.upsert(pathA, "手机", "苹果手机", 1, 4);
    db.upsert(pathB, "水果", "香蕉水果", 1, 4);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> sHits = searcher.search("", 10);
    std::vector<docseek::Hit> qHits = searcher.searchQuestion("", 10);

    EXPECT_TRUE(sHits.empty());
    EXPECT_TRUE(qHits.empty());
}