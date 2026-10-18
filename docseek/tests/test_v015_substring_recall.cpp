// 锁定子串召回（Fix B）的 E2E 行为回归网：
// 阶段 1 AND 命中、无关文档不召回、阶段 3 不污染已有结果、ASCII 大小写折叠。
#include <gtest/gtest.h>
#include <filesystem>
#include <string>
#include <vector>
#include <unistd.h>
#include "docseek/database.h"
#include "docseek/searcher.h"
#include "docseek/jieba_tokenizer.h"
#include "cppjieba/Jieba.hpp"

namespace docseek { namespace {

static long currentPid() {
    return static_cast<long>(::getpid());
}

std::string makeTempDir(const std::string& name) {
    std::filesystem::path base = std::filesystem::current_path() / "test-tmp";
    std::filesystem::create_directories(base);
    std::filesystem::path dir = base / (name + "_" + std::to_string(currentPid()));
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    return dir.string();
}

void requireJiebaReady() {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();
}

std::string basenameOf(const std::string& p) {
    return std::filesystem::path(p).filename().string();
}

// 收集命中路径的 basename 集合，便于与期望集比对。
std::vector<std::string> hitBasenames(const std::vector<Hit>& hits) {
    std::vector<std::string> out;
    out.reserve(hits.size());
    for (const auto& h : hits) out.push_back(basenameOf(h.path));
    return out;
}

bool contains(const std::vector<std::string>& v, const std::string& s) {
    for (const auto& x : v) if (x == s) return true;
    return false;
}

// (a) 命中案例：query "多肉配土配方" 应召回 doc1，命中路径为 basename。
TEST(SubstringRecallV015, HitsDoc1WithSubstringQuery) {
    requireJiebaReady();
    std::string dir = makeTempDir("v015_hit_doc1");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc1.txt").string(),
              "标题", "多肉植物配土配方比例：泥炭土加珍珠岩。", 100, 42);
    Searcher searcher(db);
    auto hits = searcher.search("多肉配土配方", 10);
    ASSERT_EQ(hits.size(), 1u);
    EXPECT_EQ(basenameOf(hits[0].path), "doc1.txt");
}

// (a) 命中案例：query "总塌腰疼" 应召回 doc2。
TEST(SubstringRecallV015, HitsDoc2WithPrefixSubstringQuery) {
    requireJiebaReady();
    std::string dir = makeTempDir("v015_hit_doc2");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc2.txt").string(),
              "标题", "总塌腰疼要按摩腰部，手法要轻。", 100, 42);
    Searcher searcher(db);
    auto hits = searcher.search("总塌腰疼", 10);
    ASSERT_EQ(hits.size(), 1u);
    EXPECT_EQ(basenameOf(hits[0].path), "doc2.txt");
}

// (b) 不命中案例：无关文档对无关 query 不应被召回。
TEST(SubstringRecallV015, DoesNotRecallUnrelatedDoc) {
    requireJiebaReady();
    std::string dir = makeTempDir("v015_nohit_unrelated");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc3.txt").string(),
              "标题", "今天天气不错，适合出门。", 100, 42);
    Searcher searcher(db);
    auto hits = searcher.search("总塌腰疼", 10);
    EXPECT_TRUE(hits.empty());
}

// (c) v0.16.1 D4 起语义变更：精确 AND 为空时丢弃 DF=0 的 token（"配方"），
// 用剩余 token（"多肉配土"）重建 AND 再查一次（fail-open 召回）。
// 因此 doc4（"多肉植物配土方法"）被召回是 D4 的意图行为（Google 式纠正/放宽后召回相关文档），
// 不是"无脑 OR 兜底"。本用例现锁定 D4 的 fail-open 召回语义。
TEST(SubstringRecallV015, Stage3DoesNotPolluteWithDoc4) {
    requireJiebaReady();
    std::string dir = makeTempDir("v015_stage3_doc4");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc4.txt").string(),
              "标题", "多肉植物配土方法", 100, 42);
    Searcher searcher(db);
    auto hits = searcher.search("多肉配土配方", 10);
    EXPECT_EQ(hits.size(), 1u);
}

// (c) 阶段 3 不污染已有结果：doc1 在阶段 1 命中，加入无关 doc3 后仍只召回 doc1。
TEST(SubstringRecallV015, Stage3DoesNotPolluteWithDoc1) {
    requireJiebaReady();
    std::string dir = makeTempDir("v015_stage3_doc1");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc1.txt").string(),
              "标题", "多肉植物配土配方比例：泥炭土加珍珠岩。", 100, 42);
    db.upsert((std::filesystem::path(dir) / "doc3.txt").string(),
              "标题", "今天天气不错，适合出门。", 100, 42);
    Searcher searcher(db);
    auto hits = searcher.search("多肉配土配方", 10);
    ASSERT_EQ(hits.size(), 1u);
    EXPECT_EQ(basenameOf(hits[0].path), "doc1.txt");
    EXPECT_FALSE(contains(hitBasenames(hits), "doc3.txt"));
}

// (d) ASCII 大小写折叠：索引侧折叠小写后，query 全小写应命中。
TEST(SubstringRecallV015, AsciiLowercaseFoldOnQuery) {
    requireJiebaReady();
    std::string dir = makeTempDir("v015_ascii_lower");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc5.txt").string(),
              "标题", "Hello World Program", 100, 42);
    Searcher searcher(db);
    auto hits = searcher.search("hello", 10);
    ASSERT_EQ(hits.size(), 1u);
    EXPECT_EQ(basenameOf(hits[0].path), "doc5.txt");
}

// (d) ASCII 大小写折叠：query 全大写也应命中（同一索引折叠）。
TEST(SubstringRecallV015, AsciiLowercaseFoldOnQueryUpper) {
    requireJiebaReady();
    std::string dir = makeTempDir("v015_ascii_upper");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc5.txt").string(),
              "标题", "Hello World Program", 100, 42);
    Searcher searcher(db);
    auto hits = searcher.search("HELLO", 10);
    ASSERT_EQ(hits.size(), 1u);
    EXPECT_EQ(basenameOf(hits[0].path), "doc5.txt");
}

// (d) ASCII 大小写折叠：无关 ASCII query 不应命中该文档。
TEST(SubstringRecallV015, AsciiUnrelatedQueryNotHit) {
    requireJiebaReady();
    std::string dir = makeTempDir("v015_ascii_unrelated");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc5.txt").string(),
              "标题", "Hello World Program", 100, 42);
    Searcher searcher(db);
    auto hits = searcher.search("goodbye", 10);
    EXPECT_TRUE(hits.empty());
}

// 组合场景：多文档并存时，命中集恰好等于期望集。
TEST(SubstringRecallV015, MultiDocHitSetExact) {
    requireJiebaReady();
    std::string dir = makeTempDir("v015_multi_doc");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc1.txt").string(),
              "标题", "多肉植物配土配方比例：泥炭土加珍珠岩。", 100, 42);
    db.upsert((std::filesystem::path(dir) / "doc3.txt").string(),
              "标题", "今天天气不错，适合出门。", 100, 42);
    db.upsert((std::filesystem::path(dir) / "doc4.txt").string(),
              "标题", "多肉植物配土方法", 100, 42);
    Searcher searcher(db);
    auto hits = searcher.search("多肉配土配方", 10);
    ASSERT_EQ(hits.size(), 1u);
    EXPECT_EQ(basenameOf(hits[0].path), "doc1.txt");
}

// 组合场景：空库查询返回空命中。
TEST(SubstringRecallV015, EmptyDatabaseReturnsNoHits) {
    requireJiebaReady();
    std::string dir = makeTempDir("v015_empty_db");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    Searcher searcher(db);
    auto hits = searcher.search("多肉配土配方", 10);
    EXPECT_TRUE(hits.empty());
}

}  // namespace
}  // namespace docseek
