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

// 直接调用真实分词 API：jiebaInstance()->CutForSearch(text, words)
// 返回分词结果；若词典初始化失败则返回空 vector 并记录错误。
std::vector<std::string> cutForSearch(const std::string& text) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        ADD_FAILURE() << "jiebaInstance() returned nullptr: "
                      << docseek::jiebaInitError();
        return {};
    }
    std::vector<std::string> words;
    jieba->CutForSearch(text, words);
    return words;
}

// 检查 words 中是否包含 token
bool contains(const std::vector<std::string>& words, const std::string& token) {
    for (const auto& w : words) {
        if (w == token) {
            return true;
        }
    }
    return false;
}

// 用端到端检索验证：把 text 写入索引，查询 query 期望至少 1 条命中。
void expectHit(const std::string& name, const std::string& text,
               const std::string& query) {
    std::string dir = makeTempDir(name);
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/doc.txt", "标题", text, 100, 42);

    docseek::Searcher searcher(db);
    auto hits = searcher.search(query, 10);
    EXPECT_GE(hits.size(), 1u) << "query=" << query << " text=" << text;
}

// 用端到端检索验证：查询 query 期望 0 条命中。
void expectMiss(const std::string& name, const std::string& text,
                const std::string& query) {
    std::string dir = makeTempDir(name);
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/doc.txt", "标题", text, 100, 42);

    docseek::Searcher searcher(db);
    auto hits = searcher.search(query, 10);
    EXPECT_TRUE(hits.empty()) << "query=" << query << " text=" << text;
}

}  // namespace

// 中华人民共和国：整词可查
TEST(TokenizerLong, PrcFullWordHit) {
    expectHit("tok_prc_full", "中华人民共和国成立于一九四九年", "中华人民共和国");
}

// 中华人民共和国：子串「中华」「人民」「共和国」也能命中
TEST(TokenizerLong, PrcSubstringsHit) {
    std::string dir = makeTempDir("tok_prc_sub");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/doc.txt", "标题", "中华人民共和国成立于一九四九年", 100, 42);

    docseek::Searcher searcher(db);

    auto hits1 = searcher.search("中华", 10);
    EXPECT_GE(hits1.size(), 1u);

    auto hits2 = searcher.search("人民", 10);
    EXPECT_GE(hits2.size(), 1u);

    auto hits3 = searcher.search("共和国", 10);
    EXPECT_GE(hits3.size(), 1u);
}

// 中华人民共和国：直接分词结果应包含整词
TEST(TokenizerLong, PrcDirectCutContainsFullWord) {
    auto words = cutForSearch("中华人民共和国成立于一九四九年");
    EXPECT_TRUE(contains(words, "中华人民共和国"))
        << "CutForSearch did not yield 中华人民共和国";
}

// 杭州师范大学：整词可查
TEST(TokenizerLong, HangzhouNormalFullWordHit) {
    expectHit("tok_hzsf_full", "杭州师范大学位于浙江省杭州市", "杭州师范大学");
}

// 杭州师范大学：子串「杭州」「师范」「大学」命中，无关词「北京」不命中
TEST(TokenizerLong, HangzhouNormalSubstringsHit) {
    std::string dir = makeTempDir("tok_hzsf_sub");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/doc.txt", "标题", "杭州师范大学位于浙江省杭州市", 100, 42);

    docseek::Searcher searcher(db);

    auto hits1 = searcher.search("杭州", 10);
    EXPECT_GE(hits1.size(), 1u);

    auto hits2 = searcher.search("师范", 10);
    EXPECT_GE(hits2.size(), 1u);

    auto hits3 = searcher.search("大学", 10);
    EXPECT_GE(hits3.size(), 1u);

    auto hits4 = searcher.search("北京", 10);
    EXPECT_TRUE(hits4.empty());
}

// 杭州师范大学：直接分词结果应包含整词
TEST(TokenizerLong, HangzhouNormalDirectCutContainsFullWord) {
    auto words = cutForSearch("杭州师范大学位于浙江省杭州市");
    EXPECT_TRUE(contains(words, "杭州师范大学"))
        << "CutForSearch did not yield 杭州师范大学";
}

// 考研数学一：整词可查
TEST(TokenizerLong, KaoyanMathOneFullWordHit) {
    expectHit("tok_kysx_full", "考研数学一复习资料整理", "考研数学一");
}

// 考研数学一：子串「考研」「数学」命中，「考研数学一」与「考研数学二」互不串
TEST(TokenizerLong, KaoyanMathOneSubstringsHit) {
    std::string dir = makeTempDir("tok_kysx_sub");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/doc.txt", "标题", "考研数学一复习资料整理", 100, 42);

    docseek::Searcher searcher(db);

    auto hits1 = searcher.search("考研", 10);
    EXPECT_GE(hits1.size(), 1u);

    auto hits2 = searcher.search("数学", 10);
    EXPECT_GE(hits2.size(), 1u);

    auto hits3 = searcher.search("考研数学一", 10);
    EXPECT_GE(hits3.size(), 1u);

    auto hits4 = searcher.search("考研数学二", 10);
    EXPECT_TRUE(hits4.empty());
}

// 考研数学一：直接分词结果应包含整词
TEST(TokenizerLong, KaoyanMathOneDirectCutContainsFullWord) {
    auto words = cutForSearch("考研数学一复习资料整理");
    EXPECT_TRUE(contains(words, "考研数学一"))
        << "CutForSearch did not yield 考研数学一";
}

// 长词完整性：整词命中数不少于子串命中数
TEST(TokenizerLong, FullWordNotLessThanSubstring) {
    std::string dir = makeTempDir("tok_full_vs_sub");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/a.txt", "标题", "中华人民共和国杭州师范大学考研数学一", 100, 42);
    db.upsert("/b.txt", "标题", "中华人民共和国", 100, 42);

    docseek::Searcher searcher(db);

    auto full = searcher.search("中华人民共和国", 10);
    auto sub = searcher.search("中华", 10);

    EXPECT_GE(full.size(), 1u);
    EXPECT_GE(sub.size(), full.size());
}

// 多个长词出现在同一文档，逐个整词检索都能命中
TEST(TokenizerLong, MultipleLongWordsInOneDoc) {
    std::string dir = makeTempDir("tok_multi_long");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/doc.txt", "标题",
              "中华人民共和国杭州师范大学考研数学一考点汇总", 100, 42);

    docseek::Searcher searcher(db);

    auto hits1 = searcher.search("中华人民共和国", 10);
    EXPECT_GE(hits1.size(), 1u);

    auto hits2 = searcher.search("杭州师范大学", 10);
    EXPECT_GE(hits2.size(), 1u);

    auto hits3 = searcher.search("考研数学一", 10);
    EXPECT_GE(hits3.size(), 1u);
}

// 多个长词出现在同一文档：直接分词应同时包含全部三个整词
TEST(TokenizerLong, MultipleLongWordsDirectCut) {
    auto words = cutForSearch("中华人民共和国杭州师范大学考研数学一考点汇总");
    EXPECT_TRUE(contains(words, "中华人民共和国"));
    EXPECT_TRUE(contains(words, "杭州师范大学"));
    EXPECT_TRUE(contains(words, "考研数学一"));
}

// 长词跨文档区分：只写在 A 文档的词不应命中 B 文档
TEST(TokenizerLong, LongWordOnlyInMatchingDoc) {
    std::string dir = makeTempDir("tok_long_cross");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/a.txt", "标题", "杭州师范大学招生简章", 100, 42);
    db.upsert("/b.txt", "标题", "北京师范大学招生简章", 100, 42);

    docseek::Searcher searcher(db);

    auto hits1 = searcher.search("杭州师范大学", 10);
    EXPECT_GE(hits1.size(), 1u);

    auto hits2 = searcher.search("北京师范大学", 10);
    EXPECT_GE(hits2.size(), 1u);

    auto hits3 = searcher.search("杭州师范大学", 10);
    for (const auto& h : hits3) {
        EXPECT_EQ(h.path, "/a.txt");
    }
}

// 边界：空文本查询长词返回空
TEST(TokenizerLong, EmptyDocNoHit) {
    std::string dir = makeTempDir("tok_empty_doc");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/doc.txt", "标题", "", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("中华人民共和国", 10);
    EXPECT_TRUE(hits.empty());

    auto hits2 = searcher.search("杭州师范大学", 10);
    EXPECT_TRUE(hits2.empty());
}

// 边界：查询串与文档串完全无关时返回空
TEST(TokenizerLong, UnrelatedQueryNoHit) {
    std::string dir = makeTempDir("tok_unrelated");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/doc.txt", "标题", "中华人民共和国", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("量子纠缠现象", 10);
    EXPECT_TRUE(hits.empty());

    auto hits2 = searcher.search("考研数学二", 10);
    EXPECT_TRUE(hits2.empty());
}

// 边界：长词与短词同时出现，短词不应吞掉长词命中
TEST(TokenizerLong, ShortAndLongCoexist) {
    std::string dir = makeTempDir("tok_short_long");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/doc.txt", "标题",
              "数学是基础，考研数学一是重点，中华人民共和国是考点", 100, 42);

    docseek::Searcher searcher(db);

    auto hitsShort = searcher.search("数学", 10);
    EXPECT_GE(hitsShort.size(), 1u);

    auto hitsLong = searcher.search("考研数学一", 10);
    EXPECT_GE(hitsLong.size(), 1u);

    auto hitsPrc = searcher.search("中华人民共和国", 10);
    EXPECT_GE(hitsPrc.size(), 1u);
}