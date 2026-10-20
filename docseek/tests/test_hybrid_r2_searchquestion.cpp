#include <gtest/gtest.h>

#include <filesystem>
#include <string>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

std::string makeUniqueDir(const std::string& name) {
    fs::path base = fs::current_path() / "test-tmp" / name;
    fs::remove_all(base);
    fs::create_directories(base);
    return base.string();
}

void seedDocs(docseek::Database& db) {
    db.upsert("docA.txt", "技术", "苹果香蕉都是水果", 1000, 100);
    db.upsert("docB.txt", "手机", "苹果手机评测", 2000, 200);
}

bool containsPath(const std::vector<docseek::Hit>& hits, const std::string& path) {
    for (const auto& h : hits) {
        if (h.path == path) return true;
    }
    return false;
}

int indexOfPath(const std::vector<docseek::Hit>& hits, const std::string& path) {
    for (size_t i = 0; i < hits.size(); ++i) {
        if (hits[i].path == path) return static_cast<int>(i);
    }
    return -1;
}

}  // namespace

TEST(HybridSearchQuestionR2, UnionOfAndAndOrReturnsBothDocs) {
    const std::string dir = makeUniqueDir("hsq_r2_union");
    docseek::Database db = docseek::Database::open(dir + "/x.db");
    seedDocs(db);

    docseek::Searcher searcher(db);
    auto hits = searcher.searchQuestion("苹果 香蕉", 10);

    EXPECT_TRUE(containsPath(hits, "docA.txt"));
    EXPECT_TRUE(containsPath(hits, "docB.txt"));
}

TEST(HybridSearchQuestionR2, DocWithAllTokensRanksBeforePartialMatch) {
    const std::string dir = makeUniqueDir("hsq_r2_order");
    docseek::Database db = docseek::Database::open(dir + "/x.db");
    seedDocs(db);

    docseek::Searcher searcher(db);
    auto hits = searcher.searchQuestion("苹果 香蕉", 10);

    int ia = indexOfPath(hits, "docA.txt");
    int ib = indexOfPath(hits, "docB.txt");
    ASSERT_GE(ia, 0);
    ASSERT_GE(ib, 0);
    EXPECT_LT(ia, ib);
}

TEST(HybridSearchQuestionR2, SingleTokenQueryMatchesDocB) {
    const std::string dir = makeUniqueDir("hsq_r2_single");
    docseek::Database db = docseek::Database::open(dir + "/x.db");
    seedDocs(db);

    docseek::Searcher searcher(db);
    auto hits = searcher.searchQuestion("苹果手机", 10);

    EXPECT_TRUE(containsPath(hits, "docB.txt"));
}

TEST(HybridSearchQuestionR2, StopwordOnlyQueryReturnsEmpty) {
    const std::string dir = makeUniqueDir("hsq_r2_stopword");
    docseek::Database db = docseek::Database::open(dir + "/x.db");
    seedDocs(db);

    docseek::Searcher searcher(db);
    auto hits = searcher.searchQuestion("的了在了", 10);

    EXPECT_TRUE(hits.empty());
}