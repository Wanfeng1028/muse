// v0.22.0：单 token 查询的词级 DF 剪枝回退（1.55）。
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

  TEST(WordLevelDfPrune, DropsMissingWordAndRecovers) {
    requireJiebaReady();
    std::string dir = makeTempDir("wlp_recover");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc1.txt").string(), "t1",
              "起针 针数 密度 算准", 100, 20);
    db.upsert((std::filesystem::path(dir) / "doc2.txt").string(), "t2",
              "计算 数学", 100, 20);
    db.upsert((std::filesystem::path(dir) / "doc3.txt").string(), "t3",
              "计算 物理", 100, 20);
    db.upsert((std::filesystem::path(dir) / "doc4.txt").string(), "t4",
              "计算 化学", 100, 20);
    Searcher s(db);
    auto hits = s.search("起针针数计算", 10);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(basenameOf(hits[0].path), "doc1.txt");
  }

  TEST(WordLevelDfPrune, UntouchedWhenAndAlreadyHits) {
    requireJiebaReady();
    std::string dir = makeTempDir("wlp_untouched");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc1.txt").string(), "t1",
              "起针 针数 计算 密度", 100, 20);
    Searcher s(db);
    auto hits = s.search("起针针数计算", 10);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(basenameOf(hits[0].path), "doc1.txt");
  }

  TEST(WordLevelDfPrune, FailOpenWhenPruneExhausted) {
    requireJiebaReady();
    std::string dir = makeTempDir("wlp_failopen");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());
    db.upsert((std::filesystem::path(dir) / "doc1.txt").string(), "t1",
              "苹果 香蕉", 100, 20);
    Searcher s(db);
    auto hits = s.search("甲乙丙丁", 10);
    EXPECT_TRUE(hits.empty());
  }

}  // namespace
}  // namespace docseek
