// D4 重构测试：DF-zero token 丢弃（与 D3 单字前缀逻辑兼容）。
//
// 设计要点：DF 探测的是 expandTokenOrQuery(t) 的展开表达式，而非裸 token，
// 因此 D3 的单字 CJK 前缀（"进"→`"进"*`）天然兼容。
#include <gtest/gtest.h>

#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"

namespace docseek {
namespace {

static long currentPid() { return static_cast<long>(::getpid()); }

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

// D4 核心红绿用例：零 DF 词拖累 AND 为空时，丢弃它用剩余 token 重建 AND。
// doc2 是干扰项（apple 高频）；无 D4 时走 OR 级联会把 doc1/doc2 都召回（size=2），
// 有 D4 时 stage 1.5 直接返回 AND 交集（size=1，top1=doc1）。
TEST(D4DfDrop, DropsZeroDfTokenAndRecoversAnd) {
    std::string dir = makeTempDir("d4_and_recover");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc1.txt").string(), "t1",
              "apple banana", 100, 20);
    db.upsert((std::filesystem::path(dir) / "doc2.txt").string(), "t2",
              "apple apple apple apple apple apple apple apple apple apple", 100, 20);
    Searcher s(db);
    auto hits = s.search("apple banana nosuchwordxyz", 10);
    ASSERT_EQ(hits.size(), 1u);
    EXPECT_EQ(basenameOf(hits[0].path), "doc1.txt");
}

// fail-open：全部 token 都零 DF 时不重建 AND，不崩溃，行为与今天一致（走 OR/子串）。
TEST(D4DfDrop, FailOpenWhenAllZeroDf) {
    std::string dir = makeTempDir("d4_fail_open");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc1.txt").string(), "t1",
              "hello world", 100, 20);
    Searcher s(db);
    auto hits = s.search("nosuchwordaaa nosuchwordbbb", 10);
    EXPECT_TRUE(hits.empty());
}

// AND 本来就有结果时 stage 1.5 不触发，结果一字不变。
TEST(D4DfDrop, UntouchedWhenAndHits) {
    std::string dir = makeTempDir("d4_untouched");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc1.txt").string(), "t1",
              "apple banana", 100, 20);
    Searcher s(db);
    auto hits = s.search("apple banana", 10);
    ASSERT_EQ(hits.size(), 1u);
    EXPECT_EQ(basenameOf(hits[0].path), "doc1.txt");
}

// D3 兼容契约锁：单字 CJK "进" 展开为前缀 `"进"*`，探测非空，不被丢弃。
// （这是 D4 与 D3 冲突点的回归锁：若有人改成探测裸 token，本例即红。）
TEST(D4DfDrop, CjkPrefixTokenNotDropped) {
    requireJiebaReady();
    std::string dir = makeTempDir("d4_cjk_prefix");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc1.txt").string(), "t1",
              "进站乘车须知：请提前到达车站。", 100, 20);
    Searcher s(db);
    auto hits = s.search("进 nosuchwordxyz", 10);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(basenameOf(hits[0].path), "doc1.txt");
}

}  // namespace
}  // namespace docseek
