#include <gtest/gtest.h>

#include <filesystem>
#include <string>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

fs::path makeUniqueDir(const std::string& name) {
    fs::path dir = fs::current_path() / "test-tmp" / name;
    std::error_code ec;
    fs::remove_all(dir, ec);
    fs::create_directories(dir, ec);
    return dir;
}

}  // namespace

TEST(HybridStopwordsR2, SearchQuestionAllStopwordsReturnsEmpty) {
    fs::path dir = makeUniqueDir("hybrid_stopwords_r2_all");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    db.upsert((dir / "a.txt").string(), "文档A", "这里有一些内容 的了在了", 100, 10);
    db.upsert((dir / "b.txt").string(), "文档B", "另外的内容 全文检索", 200, 20);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.searchQuestion("的了在了", 10);
    EXPECT_TRUE(hits.empty());
}

TEST(HybridStopwordsR2, SearchStopwordDoesNotThrow) {
    fs::path dir = makeUniqueDir("hybrid_stopwords_r2_single");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    db.upsert((dir / "a.txt").string(), "文档A", "这里有一些内容 的了在了", 100, 10);

    docseek::Searcher searcher(db);
    EXPECT_NO_THROW({
        std::vector<docseek::Hit> hits = searcher.search("的", 10);
        (void)hits;
    });
}

TEST(HybridStopwordsR2, NormalQueryStillHits) {
    fs::path dir = makeUniqueDir("hybrid_stopwords_r2_normal");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    db.upsert((dir / "a.txt").string(), "全文检索指南", "本文介绍全文检索的基本原理", 100, 10);
    db.upsert((dir / "b.txt").string(), "其他文档", "无关内容", 200, 20);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("全文检索", 10);
    EXPECT_FALSE(hits.empty());
    bool found = false;
    for (const auto& h : hits) {
        if (h.title == "全文检索指南") {
            found = true;
            break;
        }
    }
    EXPECT_TRUE(found);
}

TEST(HybridStopwordsR2, SearchQuestionWithTrailingStopwordStillHits) {
    fs::path dir = makeUniqueDir("hybrid_stopwords_r2_question");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    db.upsert((dir / "a.txt").string(), "全文检索指南", "本文介绍全文检索的基本原理", 100, 10);
    db.upsert((dir / "b.txt").string(), "其他文档", "无关内容", 200, 20);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.searchQuestion("全文检索的", 10);
    EXPECT_FALSE(hits.empty());
    bool found = false;
    for (const auto& h : hits) {
        if (h.title == "全文检索指南") {
            found = true;
            break;
        }
    }
    EXPECT_TRUE(found);
}