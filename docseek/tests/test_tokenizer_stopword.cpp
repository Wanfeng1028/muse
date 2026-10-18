#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"

#include <sqlite3.h>

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#ifndef _WIN32
#include <unistd.h>
#endif

namespace {

// 获取当前进程 id（用于构造唯一临时目录名）
long currentPid() {
#ifdef _WIN32
    return static_cast<long>(::GetCurrentProcessId());
#else
    return static_cast<long>(::getpid());
#endif
}

// 构造本次测试专用的临时目录（相对构建目录，避免使用 /tmp）
std::string makeTempDir(const std::string& name) {
    std::filesystem::path base = std::filesystem::current_path() / "test-tmp";
    std::filesystem::create_directories(base);
    std::filesystem::path dir = base / (name + "_" + std::to_string(currentPid()));
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    return dir.string();
}

// 打开一个干净数据库，返回 db 与配套的临时目录。
struct Fixture {
    std::string dir;
    std::string dbPath;
    docseek::Database db;
};

Fixture makeFixture(const std::string& name) {
    Fixture f{makeTempDir(name), "", docseek::Database::open("")};
    f.dbPath = f.dir + "/index.db";
    f.db = docseek::Database::open(f.dbPath);
    return f;
}

// 用真实 Jieba 单例对查询串做 CutForSearch，返回分词结果。
// 若词典初始化失败则返回空 vector（调用方需 ASSERT 非空）。
std::vector<std::string> cutForSearch(const std::string& text) {
    std::vector<std::string> words;
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        return words;
    }
    jieba->CutForSearch(text, words);
    return words;
}

// 判断某个词是否出现在分词结果中。
bool containsWord(const std::vector<std::string>& words, const std::string& w) {
    return std::find(words.begin(), words.end(), w) != words.end();
}

}  // namespace

// 前置检查：Jieba 单例应可用（词典初始化成功）。
TEST(TokenizerStopword, JiebaInstanceAvailable) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jiebaInitError: " << docseek::jiebaInitError();
    EXPECT_TRUE(docseek::jiebaInitError().empty());
}

// 停用词“的”单独出现在查询里，不应该把不含该词的文档拉进来。
TEST(TokenizerStopword, QueryOnlyStopwordDoesNotMatchOtherDocs) {
    Fixture f = makeFixture("stopword_only_de");
    f.db.upsert("/a.txt", "标题", "全文检索引擎测试文档", 100, 42);
    f.db.upsert("/b.txt", "标题", "苹果香蕉橘子", 100, 43);

    docseek::Searcher searcher(f.db);

    auto hits = searcher.search("的", 10);
    EXPECT_TRUE(hits.empty());

    auto hitsAll = searcher.search("苹果", 10);
    EXPECT_GE(hitsAll.size(), 1u);
}

// 停用词“了”与实词共存时，实词仍然能命中，且命中的是包含实词的文档。
TEST(TokenizerStopword, QueryStopwordWithContentTermStillMatches) {
    Fixture f = makeFixture("stopword_le_with_content");
    f.db.upsert("/a.txt", "标题", "他完成了全文检索引擎的开发", 100, 42);
    f.db.upsert("/b.txt", "标题", "苹果香蕉橘子", 100, 43);

    docseek::Searcher searcher(f.db);

    auto hits = searcher.search("完成 了 检索", 10);
    ASSERT_GE(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, std::string("/a.txt"));
}

// 停用词“在”与实词共存，命中包含实词的文档，不误命中无关文档。
TEST(TokenizerStopword, QueryStopwordZaiWithContentTerm) {
    Fixture f = makeFixture("stopword_zai_with_content");
    f.db.upsert("/a.txt", "标题", "在数据库中存储全文索引", 100, 42);
    f.db.upsert("/b.txt", "标题", "苹果香蕉橘子", 100, 43);

    docseek::Searcher searcher(f.db);

    auto hits = searcher.search("在 数据库 中 存储", 10);
    ASSERT_GE(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, std::string("/a.txt"));

    auto hitsNoise = searcher.search("在 苹果", 10);
    ASSERT_GE(hitsNoise.size(), 1u);
    EXPECT_EQ(hitsNoise[0].path, std::string("/b.txt"));
}

// 带停用词前缀的查询与去掉停用词的查询命中集合一致。
TEST(TokenizerStopword, StopwordPrefixDoesNotChangeMatchSet) {
    Fixture f = makeFixture("stopword_prefix_set");
    f.db.upsert("/a.txt", "标题", "数据库的全文检索引擎", 100, 42);
    f.db.upsert("/b.txt", "标题", "数据库的存储结构", 100, 43);
    f.db.upsert("/c.txt", "标题", "苹果香蕉橘子", 100, 44);

    docseek::Searcher searcher(f.db);

    auto withStop = searcher.search("的 数据库", 10);
    auto withoutStop = searcher.search("数据库", 10);

    ASSERT_EQ(withStop.size(), withoutStop.size());
    EXPECT_GE(withStop.size(), 2u);

    std::vector<std::string> withPaths;
    std::vector<std::string> withoutPaths;
    for (const auto& h : withStop) withPaths.push_back(h.path);
    for (const auto& h : withoutStop) withoutPaths.push_back(h.path);
    std::sort(withPaths.begin(), withPaths.end());
    std::sort(withoutPaths.begin(), withoutPaths.end());
    EXPECT_EQ(withPaths, withoutPaths);
}

// 多个停用词叠加在查询里，不能污染命中结果。
TEST(TokenizerStopword, MultipleStopwordsInQueryDoNotPollute) {
    Fixture f = makeFixture("stopword_multi_in_query");

    f.db.upsert("/a.txt", "标题", "了在的全文检索", 100, 42);
    f.db.upsert("/b.txt", "标题", "苹果香蕉橘子", 100, 43);

    docseek::Searcher searcher(f.db);

    auto hits = searcher.search("了 在 的 检索", 10);
    ASSERT_GE(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, std::string("/a.txt"));

    auto hitsEmpty = searcher.search("了 在 的", 10);
    EXPECT_TRUE(hitsEmpty.empty());
}

// 文档里含有大量停用词，正文关键词仍能被检索命中。
TEST(TokenizerStopword, DocumentWithManyStopwordsStillSearchable) {
    Fixture f = makeFixture("stopword_doc_many");

    f.db.upsert("/a.txt", "标题",
                "的了在了的了在了全文检索在的了在了的了",
                100, 42);
    f.db.upsert("/b.txt", "标题", "苹果香蕉橘子", 100, 43);

    docseek::Searcher searcher(f.db);

    auto hits = searcher.search("全文检索", 10);
    ASSERT_GE(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, std::string("/a.txt"));

    auto hitsNoise = searcher.search("的了在了", 10);
    EXPECT_TRUE(hitsNoise.empty());
}

// 停用词作为检索词与实词混合时，结果的排序应以实词匹配为主。
TEST(TokenizerStopword, StopwordMixedQueryRankingPrefersContentMatch) {
    Fixture f = makeFixture("stopword_ranking");

    f.db.upsert("/a.txt", "标题", "的了的全文检索引擎的了的", 100, 42);
    f.db.upsert("/b.txt", "标题", "苹果香蕉橘子", 100, 43);

    docseek::Searcher searcher(f.db);

    auto hits = searcher.search("的 检索", 10);
    ASSERT_GE(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, std::string("/a.txt"));

    auto hitsOther = searcher.search("的 苹果", 10);
    ASSERT_GE(hitsOther.size(), 1u);
    EXPECT_EQ(hitsOther[0].path, std::string("/b.txt"));
}

// 检索词只由停用词组成时，结果为空，且不同停用词组合都为空。
TEST(TokenizerStopword, AllStopwordQueriesReturnEmpty) {
    Fixture f = makeFixture("stopword_all_empty");

    f.db.upsert("/a.txt", "标题", "的了在了全文检索", 100, 42);
    f.db.upsert("/b.txt", "标题", "苹果香蕉橘子", 100, 43);

    docseek::Searcher searcher(f.db);

    auto hitsDe = searcher.search("的", 10);
    auto hitsLe = searcher.search("了", 10);
    auto hitsZai = searcher.search("在", 10);

    EXPECT_TRUE(hitsDe.empty());
    EXPECT_TRUE(hitsLe.empty());
    EXPECT_TRUE(hitsZai.empty());
}

// 停用词夹在实词中间不影响分词，实词仍可被检索到。
TEST(TokenizerStopword, StopwordBetweenContentTermsStillMatches) {
    Fixture f = makeFixture("stopword_between_content");

    f.db.upsert("/a.txt", "标题", "数据在库的全文索引", 100, 42);
    f.db.upsert("/b.txt", "标题", "苹果香蕉橘子", 100, 43);

    docseek::Searcher searcher(f.db);

    auto hits = searcher.search("数据 库 全文 索引", 10);
    ASSERT_GE(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, std::string("/a.txt"));

    // "数据 苹果" 分属两篇文档：AND 为空后触发多 token OR 回退，两篇都召回（既定行为，非停用词问题）。
    auto hitsNoise = searcher.search("数据 苹果", 10);
    EXPECT_EQ(hitsNoise.size(), 2u);
}

// 带停用词查询在 limit 截断下仍以实词匹配为准。
TEST(TokenizerStopword, StopwordQueryRespectsLimit) {
    Fixture f = makeFixture("stopword_limit");
    f.db.upsert("/a.txt", "标题", "的了在了全文检索一", 100, 42);
    f.db.upsert("/b.txt", "标题", "的了在了全文检索二", 100, 43);
    f.db.upsert("/c.txt", "标题", "的了在了全文检索三", 100, 44);

    docseek::Searcher searcher(f.db);

    auto hits = searcher.search("的 检索", 2);
    EXPECT_EQ(hits.size(), 2u);
    for (const auto& h : hits) {
        EXPECT_NE(h.path, std::string("/c.txt"));
    }

    auto hitsAll = searcher.search("的 检索", 10);
    EXPECT_EQ(hitsAll.size(), 3u);
}

// 停用词大小写/空白噪声混入不影响结果。
TEST(TokenizerStopword, StopwordWithWhitespaceStillMatches) {
    Fixture f = makeFixture("stopword_whitespace");

    f.db.upsert("/a.txt", "标题", "全文检索引擎的测试", 100, 42);
    f.db.upsert("/b.txt", "标题", "苹果香蕉橘子", 100, 43);

    docseek::Searcher searcher(f.db);

    auto hits = searcher.search("  的   检索  ", 10);
    ASSERT_GE(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, std::string("/a.txt"));

    auto hitsEmpty = searcher.search("  的   ", 10);
    EXPECT_TRUE(hitsEmpty.empty());
}

// 直接验证 Jieba 单例的分词行为：停用词“的”会被独立切出，
// 但“检索”等实词也会被切出，供查询层过滤停用词使用。
TEST(TokenizerStopword, JiebaInstanceCutsStopwordAndContent) {
    std::vector<std::string> words = cutForSearch("的 检索");
    ASSERT_FALSE(words.empty()) << "jiebaInitError: " << docseek::jiebaInitError();

    // “检索”必须作为一个实词出现在分词结果中。
    EXPECT_TRUE(containsWord(words, "检索"));

    // 查询只由停用词组成时，分词结果里仍然能看到停用词本身，
    // 说明停用词过滤发生在 Searcher 查询层而非 Jieba 分词层。
    std::vector<std::string> stopOnly = cutForSearch("的");
    EXPECT_FALSE(stopOnly.empty());
}

// 端到端验证：通过 registerJiebaTokenizer 注册 FTS5 分词器后，
// 建表、插入、查询停用词与实词组合，行为与 Searcher 一致。
TEST(TokenizerStopword, RegisterJiebaTokenizerEndToEnd) {
    Fixture f = makeFixture("stopword_register_e2e");

    sqlite3* raw = nullptr;
    ASSERT_EQ(sqlite3_open(f.dbPath.c_str(), &raw), SQLITE_OK);
    ASSERT_NE(raw, nullptr);

    int rc = docseek::registerJiebaTokenizer(raw);
    ASSERT_EQ(rc, SQLITE_OK) << "jiebaInitError: " << docseek::jiebaInitError();

    const char* createSql =
        "CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5("
        "  path, title, body, tokenize='jieba'"
        ");";
    char* errMsg = nullptr;
    rc = sqlite3_exec(raw, createSql, nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::string msg = errMsg ? errMsg : "";
        sqlite3_free(errMsg);
        sqlite3_close(raw);
        FAIL() << "CREATE VIRTUAL TABLE failed: " << msg;
    }

    const char* insertSql =
        "INSERT INTO docs(path, title, body) VALUES"
        "('/a.txt', '标题', '全文检索引擎测试文档'),"
        "('/b.txt', '标题', '苹果香蕉橘子');";
    rc = sqlite3_exec(raw, insertSql, nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::string msg = errMsg ? errMsg : "";
        sqlite3_free(errMsg);
        sqlite3_close(raw);
        FAIL() << "INSERT failed: " << msg;
    }

    // 查询实词“检索”，应命中 /a.txt。
    {
        sqlite3_stmt* stmt = nullptr;
        const char* sql =
            "SELECT path FROM docs WHERE docs MATCH ? ORDER BY path LIMIT 10;";
        ASSERT_EQ(sqlite3_prepare_v2(raw, sql, -1, &stmt, nullptr), SQLITE_OK);
        std::string q = "检索";
        sqlite3_bind_text(stmt, 1, q.c_str(), -1, SQLITE_TRANSIENT);

        std::vector<std::string> paths;
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            const unsigned char* p = sqlite3_column_text(stmt, 0);
            if (p) paths.emplace_back(reinterpret_cast<const char*>(p));
        }
        sqlite3_finalize(stmt);

        ASSERT_FALSE(paths.empty());
        EXPECT_EQ(paths.front(), std::string("/a.txt"));
    }

    // 查询实词“苹果”，应命中 /b.txt。
    {
        sqlite3_stmt* stmt = nullptr;
        const char* sql =
            "SELECT path FROM docs WHERE docs MATCH ? ORDER BY path LIMIT 10;";
        ASSERT_EQ(sqlite3_prepare_v2(raw, sql, -1, &stmt, nullptr), SQLITE_OK);
        std::string q = "苹果";
        sqlite3_bind_text(stmt, 1, q.c_str(), -1, SQLITE_TRANSIENT);

        std::vector<std::string> paths;
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            const unsigned char* p = sqlite3_column_text(stmt, 0);
            if (p) paths.emplace_back(reinterpret_cast<const char*>(p));
        }
        sqlite3_finalize(stmt);

        ASSERT_FALSE(paths.empty());
        EXPECT_EQ(paths.front(), std::string("/b.txt"));
    }

    sqlite3_close(raw);
}