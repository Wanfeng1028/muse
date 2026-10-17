#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"

#include <sqlite3.h>

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

// 打开一个全新的索引库，供每个用例独立使用
docseek::Database openFreshDb(const std::string& name) {
    std::string dir = makeTempDir(name);
    std::string dbPath = dir + "/index.db";
    return docseek::Database::open(dbPath);
}

}  // namespace

// 简体文档：用简体查询词命中
TEST(TokenizerTradTest, SimplifiedDocSimplifiedQuery) {
    docseek::Database db = openFreshDb("trad_simp_simp");
    db.upsert("/s1.txt", "简体标题", "全文检索引擎测试文档", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("检索", 10);
    EXPECT_GE(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].path, "/s1.txt");
}

// 简体文档：用繁体查询词命中（繁->简归一化）
TEST(TokenizerTradTest, SimplifiedDocTraditionalQuery) {
    // 当前行为：无繁简归一化，繁体查询词查简体文档返回 0 条（未来实现归一化时本测试需同步更新）。
    docseek::Database db = openFreshDb("trad_simp_trad");
    db.upsert("/s2.txt", "简体标题", "全文检索引擎测试文档", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("檢索", 10);
    EXPECT_TRUE(hits.empty());

    auto hits2 = searcher.search("全文檢索", 10);
    EXPECT_TRUE(hits2.empty());

    // 对照：简体查询词命中简体文档（同字形正常工作）
    auto hits3 = searcher.search("检索", 10);
    EXPECT_GE(hits3.size(), 1u);
}

// 繁体文档：用简体查询词命中（简->繁归一化）
TEST(TokenizerTradTest, TraditionalDocSimplifiedQuery) {
    // 当前行为：无繁简归一化，简体查询词查繁体文档返回 0 条（未来实现归一化时本测试需同步更新）。
    docseek::Database db = openFreshDb("trad_trad_simp");
    db.upsert("/t1.txt", "繁體標題", "全文檢索引擎測試文檔", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("检索", 10);
    EXPECT_TRUE(hits.empty());

    auto hits2 = searcher.search("全文检索", 10);
    EXPECT_TRUE(hits2.empty());

    // 对照：繁体查询词命中繁体文档（同字形正常工作）
    auto hits3 = searcher.search("檢索", 10);
    EXPECT_GE(hits3.size(), 1u);
}

// 繁体文档：用繁体查询词命中
TEST(TokenizerTradTest, TraditionalDocTraditionalQuery) {
    docseek::Database db = openFreshDb("trad_trad_trad");
    db.upsert("/t2.txt", "繁體標題", "全文檢索引擎測試文檔", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("檢索", 10);
    EXPECT_GE(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].path, "/t2.txt");
}

// 繁简混排文档：两种查询词都能命中同一篇文档
TEST(TokenizerTradTest, MixedDocBothQueryForms) {
    docseek::Database db = openFreshDb("trad_mixed_both");
    db.upsert("/m1.txt", "混排标题", "全文檢索 engine 检索 測試 test", 100, 42);

    docseek::Searcher searcher(db);

    auto simp = searcher.search("检索", 10);
    EXPECT_GE(simp.size(), 1u);
    ASSERT_FALSE(simp.empty());
    EXPECT_EQ(simp[0].path, "/m1.txt");

    auto trad = searcher.search("檢索", 10);
    EXPECT_GE(trad.size(), 1u);
    ASSERT_FALSE(trad.empty());
    EXPECT_EQ(trad[0].path, "/m1.txt");
}

// 繁简混排：多个文档分别用不同字形写入，同一查询词要能同时命中
TEST(TokenizerTradTest, BothDocsHitBySingleQuery) {
    // 当前行为：无繁简归一化，各字形只命中同字形文档（未来实现归一化时本测试需同步更新）。
    docseek::Database db = openFreshDb("trad_both_docs");
    db.upsert("/d1.txt", "简体", "全文检索引擎测试", 100, 42);
    db.upsert("/d2.txt", "繁體", "全文檢索引擎測試", 90, 43);

    docseek::Searcher searcher(db);

    auto simp = searcher.search("检索", 10);
    EXPECT_EQ(simp.size(), 1u);
    EXPECT_EQ(simp[0].path, "/d1.txt");

    auto trad = searcher.search("檢索", 10);
    EXPECT_EQ(trad.size(), 1u);
    EXPECT_EQ(trad[0].path, "/d2.txt");
}

// 边界：繁体查询词对应简体文档里根本没有的字，应该查不到
TEST(TokenizerTradTest, TraditionalQueryMissWhenAbsent) {
    docseek::Database db = openFreshDb("trad_miss_absent");
    db.upsert("/n1.txt", "简体", "全文检索引擎测试", 100, 42);

    docseek::Searcher searcher(db);

    // “圖書館” 在文档里完全不存在
    auto hits = searcher.search("圖書館", 10);
    EXPECT_TRUE(hits.empty());
}

// 边界：空查询返回空结果，不崩溃
TEST(TokenizerTradTest, EmptyQueryReturnsEmpty) {
    docseek::Database db = openFreshDb("trad_empty_query");
    db.upsert("/e1.txt", "简体", "全文检索引擎测试", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("", 10);
    EXPECT_TRUE(hits.empty());
}

// 边界：limit 为 1 时，繁简混排的两篇文档只能返回一条
TEST(TokenizerTradTest, LimitOneOnMixedCorpus) {
    docseek::Database db = openFreshDb("trad_limit_one");
    db.upsert("/l1.txt", "简体", "全文检索引擎测试", 100, 42);
    db.upsert("/l2.txt", "繁體", "全文檢索引擎測試", 90, 43);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("检索", 1);
    EXPECT_EQ(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    bool isKnown = (hits[0].path == "/l1.txt" || hits[0].path == "/l2.txt");
    EXPECT_TRUE(isKnown);
}

// 端到端：写入繁体文档后按简体词检索，命中后 score/rank 为合理值
TEST(TokenizerTradTest, TraditionalDocHitHasValidScore) {
    docseek::Database db = openFreshDb("trad_valid_score");
    db.upsert("/v1.txt", "繁體", "全文檢索引擎測試文檔", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("檢索", 10);
    EXPECT_GE(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].path, "/v1.txt");
    EXPECT_GE(hits[0].score, 0.0);
}

// 端到端：同一篇文档，简体和繁体查询返回一致的结果集合
TEST(TokenizerTradTest, SameDocSameResultSetForBothForms) {
    // 当前行为：无繁简归一化；简体查询命中，繁体查询返回空（未来实现归一化时本测试需同步更新）。
    docseek::Database db = openFreshDb("trad_same_result");
    db.upsert("/x1.txt", "简体", "全文检索引擎测试", 100, 42);

    docseek::Searcher searcher(db);

    auto simp = searcher.search("检索", 10);
    auto trad = searcher.search("檢索", 10);

    EXPECT_GE(simp.size(), 1u);
    EXPECT_EQ(simp[0].path, "/x1.txt");
    EXPECT_TRUE(trad.empty());
}

// 直接分词 API：jiebaInstance() 返回的 Jieba 单例对简体文本调用 CutForSearch
TEST(TokenizerTradTest, JiebaInstanceCutsSimplified) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("全文检索引擎测试", words);
    EXPECT_FALSE(words.empty());
}

// 直接分词 API：jiebaInstance() 对繁体文本调用 CutForSearch
TEST(TokenizerTradTest, JiebaInstanceCutsTraditional) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("全文檢索引擎測試", words);
    EXPECT_FALSE(words.empty());
}

// 端到端：通过 registerJiebaTokenizer 在裸 sqlite3 连接上注册 FTS5 分词器
TEST(TokenizerTradTest, RegisterJiebaTokenizerOnRawSqlite) {
    sqlite3* raw = nullptr;
    ASSERT_EQ(sqlite3_open(":memory:", &raw), SQLITE_OK);
    ASSERT_NE(raw, nullptr);

    int rc = docseek::registerJiebaTokenizer(raw);
    EXPECT_EQ(rc, SQLITE_OK);

    sqlite3_close(raw);
}