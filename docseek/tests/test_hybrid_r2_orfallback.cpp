#include <gtest/gtest.h>

#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

struct TempDir {
    fs::path path;
    TempDir(const std::string& name) {
        path = fs::current_path() / "test-tmp" / name;
        fs::create_directories(path);
    }
    ~TempDir() {
        std::error_code ec;
        fs::remove_all(path, ec);
    }
    std::string dbPath() const { return (path / "x.db").string(); }
};

bool containsPath(const std::vector<docseek::Hit>& hits, const std::string& path) {
    for (const auto& h : hits) {
        if (h.path == path) return true;
    }
    return false;
}

void setupDocs(docseek::Database& db, const fs::path& dir,
               const std::string& nameA, const std::string& titleA, const std::string& contentA,
               const std::string& nameB, const std::string& titleB, const std::string& contentB,
               const std::string& nameC, const std::string& titleC, const std::string& contentC,
               std::string& pathA, std::string& pathB, std::string& pathC) {
    pathA = (dir / nameA).string();
    pathB = (dir / nameB).string();
    pathC = (dir / nameC).string();
    db.upsert(pathA, titleA, contentA, 1000, 100);
    db.upsert(pathB, titleB, contentB, 1000, 100);
    db.upsert(pathC, titleC, contentC, 1000, 100);
}

}  // namespace

TEST(HybridOrFallbackR2, OrFallbackHitsBothDocs) {
    TempDir td("hybrid_or_r2_case1");
    docseek::Database db = docseek::Database::open(td.dbPath());
    std::string pathA, pathB, pathC;
    setupDocs(db, td.path,
              "a.txt", "手机", "苹果手机评测",
              "b.txt", "水果", "香蕉营养价值",
              "c.txt", "无关", "今天天气不错",
              pathA, pathB, pathC);
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("苹果 香蕉", 10);
    EXPECT_TRUE(containsPath(hits, pathA));
    EXPECT_TRUE(containsPath(hits, pathB));
}

TEST(HybridOrFallbackR2, UnrelatedDocExcluded) {
    TempDir td("hybrid_or_r2_case2");
    docseek::Database db = docseek::Database::open(td.dbPath());
    std::string pathA, pathB, pathC;
    setupDocs(db, td.path,
              "a.txt", "手机", "苹果手机评测",
              "b.txt", "水果", "香蕉营养价值",
              "c.txt", "无关", "今天天气不错",
              pathA, pathB, pathC);
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("苹果 香蕉", 10);
    EXPECT_FALSE(containsPath(hits, pathC));
}

TEST(HybridOrFallbackR2, AndPathHitsDocA) {
    TempDir td("hybrid_or_r2_case3");
    docseek::Database db = docseek::Database::open(td.dbPath());
    std::string pathA, pathB, pathC;
    setupDocs(db, td.path,
              "a.txt", "手机", "苹果手机评测",
              "b.txt", "水果", "香蕉营养价值",
              "c.txt", "无关", "今天天气不错",
              pathA, pathB, pathC);
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("苹果手机 香蕉", 10);
    EXPECT_TRUE(containsPath(hits, pathA));
}

TEST(HybridOrFallbackR2, OrFallbackWithUnknownToken) {
    TempDir td("hybrid_or_r2_case4");
    docseek::Database db = docseek::Database::open(td.dbPath());
    std::string pathA, pathB, pathC;
    setupDocs(db, td.path,
              "a.txt", "手机", "苹果手机评测",
              "b.txt", "水果", "香蕉营养价值",
              "c.txt", "无关", "今天天气不错",
              pathA, pathB, pathC);
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("苹果 不存在词XYZ", 10);
    EXPECT_TRUE(containsPath(hits, pathA));
    EXPECT_FALSE(containsPath(hits, pathB));
    EXPECT_FALSE(containsPath(hits, pathC));
}