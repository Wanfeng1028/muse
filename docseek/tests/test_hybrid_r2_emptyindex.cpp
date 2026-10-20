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

TEST(HybridEmptyIndexR2, SearchOnEmptyIndexReturnsEmpty) {
    fs::path dir = makeTempDir("hybrid_r2_empty_search");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    docseek::Searcher searcher(db);

    std::vector<docseek::Hit> hits = searcher.search("检索", 10);
    EXPECT_TRUE(hits.empty());
}

TEST(HybridEmptyIndexR2, SearchQuestionOnEmptyIndexReturnsEmpty) {
    fs::path dir = makeTempDir("hybrid_r2_empty_searchquestion");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    docseek::Searcher searcher(db);

    std::vector<docseek::Hit> hits = searcher.searchQuestion("全文检索怎么办", 10);
    EXPECT_TRUE(hits.empty());
}

TEST(HybridEmptyIndexR2, ExplainOnEmptyIndexReturnsEmpty) {
    fs::path dir = makeTempDir("hybrid_r2_empty_explain");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    docseek::Searcher searcher(db);

    std::vector<docseek::ExplainedHit> hits = searcher.explain("检索", 10);
    EXPECT_TRUE(hits.empty());
}

TEST(HybridEmptyIndexR2, UpsertAfterEmptySearchMakesIndexUsable) {
    fs::path dir = makeTempDir("hybrid_r2_empty_then_upsert");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    docseek::Searcher searcher(db);

    std::vector<docseek::Hit> before = searcher.search("检索", 10);
    EXPECT_TRUE(before.empty());

    db.upsert((dir / "doc.txt").string(), "全文检索", "全文检索的正文内容", 1000, 42);

    std::vector<docseek::Hit> after = searcher.search("检索", 10);
    EXPECT_FALSE(after.empty());
}