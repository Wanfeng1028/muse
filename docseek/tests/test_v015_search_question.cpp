// 锁定 Searcher::searchQuestion 的 AND/OR 并集语义。
// 关键行为：阶段 2 恒执行 OR（tokens.size()>=2），与 search() 的"仅 AND 为空时 OR"形成差异。
// GAP-TOK-001：单 token 不执行 OR，本测试只锁定现状，不测修复后行为。
#include <gtest/gtest.h>

#include <algorithm>
#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"
#include "docseek/jieba_tokenizer.h"

namespace docseek {
namespace {

// 取进程 pid，用于隔离并发测试进程的临时目录
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

// 取 path 的 basename，断言用
std::string baseName(const std::string& path) {
    return std::filesystem::path(path).filename().string();
}

// 收集命中集合的 basename 列表
std::vector<std::string> baseNames(const std::vector<Hit>& hits) {
    std::vector<std::string> names;
    names.reserve(hits.size());
    for (const auto& h : hits) {
        names.push_back(baseName(h.path));
    }
    return names;
}

bool containsName(const std::vector<Hit>& hits, const std::string& name) {
    for (const auto& h : hits) {
        if (baseName(h.path) == name) {
            return true;
        }
    }
    return false;
}

// 断言 path 无重复
void expectNoDuplicatePaths(const std::vector<Hit>& hits) {
    std::vector<std::string> paths;
    paths.reserve(hits.size());
    for (const auto& h : hits) {
        paths.push_back(h.path);
    }
    std::sort(paths.begin(), paths.end());
    auto it = std::adjacent_find(paths.begin(), paths.end());
    EXPECT_EQ(it, paths.end()) << "命中结果中出现重复 path";
}

// 语料 A：docA 正文含"苹果手机"，docB 正文含"苹果"但不含"手机"。
// 这样 query "苹果 手机" 时：AND 命中 docA；OR 并集带入 docB。
void seedAppleCorpus(Database& db) {
    db.upsert("/docA.txt", "手机评测", "苹果手机很好用", 100, 42);
    db.upsert("/docB.txt", "美食教程", "香蕉苹果派的做法", 100, 42);
}

// ===== (a) searchQuestion 并集语义 =====
TEST(SearchQuestionV015, UnionBringsOrOnlyDoc) {
    requireJiebaReady();
    const std::string dir = makeTempDir("sq_union");
    Database db = Database::open(dir + "/sq_union.db");
    seedAppleCorpus(db);
    Searcher searcher(db);

    auto hits = searcher.searchQuestion("苹果 手机", 10);

    // AND 命中 docA；OR 命中 docB；并集 => 两篇都在
    ASSERT_EQ(hits.size(), 2u);
    EXPECT_TRUE(containsName(hits, "docA.txt"));
    EXPECT_TRUE(containsName(hits, "docB.txt"));
    expectNoDuplicatePaths(hits);
}

// ===== (a) AND 版本优先排在前面 =====
TEST(SearchQuestionV015, AndVersionRanksFirst) {
    requireJiebaReady();
    const std::string dir = makeTempDir("sq_and_first");
    Database db = Database::open(dir + "/sq_and_first.db");
    seedAppleCorpus(db);
    Searcher searcher(db);

    auto hits = searcher.searchQuestion("苹果 手机", 10);

    ASSERT_FALSE(hits.empty());
    // 冲突时保留 AND 版本（docA），因此 docA 应排在 docB 之前
    EXPECT_EQ(baseName(hits.front().path), "docA.txt");
}

// ===== (b) search() 与 searchQuestion() 的行为差异 =====
// search(): AND 非空时不再 OR，故仅 docA；searchQuestion(): 恒 OR，故 docA + docB。
TEST(SearchQuestionV015, SearchDoesNotUnionWhenAndNonEmpty) {
    requireJiebaReady();
    const std::string dir = makeTempDir("sq_diff");
    Database db = Database::open(dir + "/sq_diff.db");
    seedAppleCorpus(db);
    Searcher searcher(db);

    auto searchHits = searcher.search("苹果 手机", 10);
    auto questionHits = searcher.searchQuestion("苹果 手机", 10);

    // search(): AND 命中 docA，不再 OR => 只返回 docA
    ASSERT_FALSE(searchHits.empty());
    EXPECT_TRUE(containsName(searchHits, "docA.txt"));
    EXPECT_FALSE(containsName(searchHits, "docB.txt"));
    EXPECT_EQ(searchHits.size(), 1u);

    // searchQuestion(): 恒 OR => docA + docB
    EXPECT_TRUE(containsName(questionHits, "docA.txt"));
    EXPECT_TRUE(containsName(questionHits, "docB.txt"));
    EXPECT_EQ(questionHits.size(), 2u);
}

// ===== (c) 无 AND 命中时两者一致 =====
// query "苹果 榴莲"：AND 为空（无文档同时含二者）；两者都走 OR 分支。
TEST(SearchQuestionV015, SameWhenAndEmpty) {
    requireJiebaReady();
    const std::string dir = makeTempDir("sq_and_empty");
    Database db = Database::open(dir + "/sq_and_empty.db");
    seedAppleCorpus(db);
    Searcher searcher(db);

    auto searchHits = searcher.search("苹果 榴莲", 10);
    auto questionHits = searcher.searchQuestion("苹果 榴莲", 10);

    auto sNames = baseNames(searchHits);
    auto qNames = baseNames(questionHits);
    std::sort(sNames.begin(), sNames.end());
    std::sort(qNames.begin(), qNames.end());
    EXPECT_EQ(sNames, qNames);
    // OR 命中：docA、docB 都含"苹果"
    EXPECT_TRUE(containsName(searchHits, "docA.txt"));
    EXPECT_TRUE(containsName(searchHits, "docB.txt"));
}

// ===== (d) AND/OR 同时命中同一 doc 时只出现一次 =====
// query "苹果 苹果"：两个 token 相同，AND 与 OR 都会命中两篇文档。
TEST(SearchQuestionV015, NoDuplicateWhenAndAndOrOverlap) {
    requireJiebaReady();
    const std::string dir = makeTempDir("sq_dedup");
    Database db = Database::open(dir + "/sq_dedup.db");
    seedAppleCorpus(db);
    Searcher searcher(db);

    auto hits = searcher.searchQuestion("苹果 苹果", 10);

    expectNoDuplicatePaths(hits);
    // 两篇文档都含"苹果"，AND（同词）与 OR 并集后应为两篇
    EXPECT_EQ(hits.size(), 2u);
}

// ===== (d) 单篇语料下 AND/OR 重叠不产生重复 =====
TEST(SearchQuestionV015, NoDuplicateSingleDoc) {
    requireJiebaReady();
    const std::string dir = makeTempDir("sq_dedup_single");
    Database db = Database::open(dir + "/sq_dedup_single.db");
    db.upsert("/docA.txt", "手机评测", "苹果手机很好用", 100, 42);
    Searcher searcher(db);

    auto hits = searcher.searchQuestion("苹果 手机", 10);

    expectNoDuplicatePaths(hits);
    ASSERT_EQ(hits.size(), 1u);
    EXPECT_EQ(baseName(hits.front().path), "docA.txt");
}

// ===== (e) limit 截断 =====
// 三篇文档都含"苹果"，query "苹果 手机" 的 OR 并集应被 limit 截断。
TEST(SearchQuestionV015, RespectsLimit) {
    requireJiebaReady();
    const std::string dir = makeTempDir("sq_limit");
    Database db = Database::open(dir + "/sq_limit.db");
    db.upsert("/docA.txt", "手机评测", "苹果手机很好用", 100, 42);
    db.upsert("/docB.txt", "美食教程", "香蕉苹果派的做法", 100, 42);
    db.upsert("/docC.txt", "水果介绍", "苹果的营养价值很高", 100, 42);
    Searcher searcher(db);

    auto hits = searcher.searchQuestion("苹果 手机", 2);

    EXPECT_LE(hits.size(), 2u);
    expectNoDuplicatePaths(hits);
}

// ===== (e) limit 大于结果数时不截断 =====
TEST(SearchQuestionV015, LimitLargerThanResults) {
    requireJiebaReady();
    const std::string dir = makeTempDir("sq_limit_big");
    Database db = Database::open(dir + "/sq_limit_big.db");
    seedAppleCorpus(db);
    Searcher searcher(db);

    auto hits = searcher.searchQuestion("苹果 手机", 100);

    EXPECT_EQ(hits.size(), 2u);
    expectNoDuplicatePaths(hits);
}

}  // namespace
}  // namespace docseek