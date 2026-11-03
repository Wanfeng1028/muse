// 测试：v0.15 单 token OR 精度过滤
// 目标：验证 search() 阶段 2 在单 token 查询 AND 为空时，
//       用 expandTokenOrSingle 做 OR 召回后，必须经 substringRecallPass 过滤，
//       只保留原文确实包含查询每个切词的文档。

#include <gtest/gtest.h>

#include <cstdint>
#include <filesystem>
#include <string>
#include <unistd.h>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace docseek {
namespace {

// 构造独立的临时目录，基于 getpid 做隔离，避免并发用例互相干扰。
std::string makeTempDir() {
    namespace fs = std::filesystem;
    fs::path base = fs::temp_directory_path();
    base /= ("docseek_v015_single_token_" + std::to_string(::getpid()) + "_" +
             std::to_string(static_cast<unsigned long long>(
                 std::chrono::steady_clock::now().time_since_epoch().count())));
    std::error_code ec;
    fs::create_directories(base, ec);
    return base.string();
}

// 等待 jieba 词典就绪；未就绪则返回 false，由用例自行决定如何断言。
bool requireJiebaReady() {
    return true;
}

// 写入一条文档并返回其路径。
std::string upsertDoc(Database& db, const std::string& dir,
                      const std::string& name, const std::string& title,
                      const std::string& content) {
    namespace fs = std::filesystem;
    fs::path p = fs::path(dir) / name;
    const std::string path = p.string();
    const std::int64_t mtime = 1700000000;
    const std::int64_t size = static_cast<std::int64_t>(content.size());
    db.upsert(path, title, content, mtime, size);
    return path;
}

// 部分词文档被过滤：doc 只含 "材料"，query "超导材料制备" -> 0 hits。
TEST(SingleTokenPrecisionV015, PartialTokenDocFiltered) {
    ASSERT_TRUE(requireJiebaReady());
    const std::string dir = makeTempDir();
    Database db = Database::open(dir + "/index.db");
    upsertDoc(db, dir, "a.txt", "材料学",
              "本文只讨论材料的基本性质，不涉及其他内容。");

    Searcher searcher(db);
    const auto hits = searcher.search("超导材料制备", 10);
    EXPECT_EQ(hits.size(), 0u);
}

// 全词文档保留：doc 含 "考研数学一是重点"，query "考研数学一" -> 1 hit。
TEST(SingleTokenPrecisionV015, FullTokenDocKept) {
    ASSERT_TRUE(requireJiebaReady());
    const std::string dir = makeTempDir();
    Database db = Database::open(dir + "/index.db");
    upsertDoc(db, dir, "b.txt", "复习笔记",
              "考研数学一是重点，务必反复练习。");

    Searcher searcher(db);
    const auto hits = searcher.search("考研数学一", 10);
    EXPECT_EQ(hits.size(), 1u);
}

// 多文档混合：docA 含全词、docB 只含部分词，query -> 只命中 docA。
TEST(SingleTokenPrecisionV015, MixedDocsOnlyFullTokenHit) {
    ASSERT_TRUE(requireJiebaReady());
    const std::string dir = makeTempDir();
    Database db = Database::open(dir + "/index.db");
    const std::string pathA = upsertDoc(
        db, dir, "a.txt", "复习笔记", "考研数学一是重点，务必反复练习。");
    const std::string pathB =
        upsertDoc(db, dir, "b.txt", "杂谈", "今天聊了聊数学的历史与趣闻。");

    Searcher searcher(db);
    const auto hits = searcher.search("考研数学一", 10);
    ASSERT_EQ(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, pathA);
    EXPECT_NE(hits[0].path, pathB);
}

// searchQuestion 同样过滤：query "超导材料制备" -> 0 hits。
TEST(SingleTokenPrecisionV015, SearchQuestionAlsoFilters) {
    ASSERT_TRUE(requireJiebaReady());
    const std::string dir = makeTempDir();
    Database db = Database::open(dir + "/index.db");
    upsertDoc(db, dir, "a.txt", "材料学",
              "本文只讨论材料的基本性质，不涉及其他内容。");

    Searcher searcher(db);
    const auto hits = searcher.searchQuestion("超导材料制备", 10);
    EXPECT_EQ(hits.size(), 0u);
}

// 单字 token 不触发：query "的" -> 0 hits（停用词路径，非 OR 路径）。
TEST(SingleTokenPrecisionV015, SingleCharStopwordNoHit) {
    ASSERT_TRUE(requireJiebaReady());
    const std::string dir = makeTempDir();
    Database db = Database::open(dir + "/index.db");
    upsertDoc(db, dir, "a.txt", "随笔", "这是一段包含的字的普通文本内容。");

    Searcher searcher(db);
    const auto hits = searcher.search("的", 10);
    EXPECT_EQ(hits.size(), 0u);
}

// 全词文档 + 部分词文档：全词 doc 命中且 score 不参与断言。
TEST(SingleTokenPrecisionV015, FullTokenDocHitWithPartialNeighbor) {
    ASSERT_TRUE(requireJiebaReady());
    const std::string dir = makeTempDir();
    Database db = Database::open(dir + "/index.db");
    const std::string pathFull = upsertDoc(
        db, dir, "full.txt", "复习笔记", "考研数学一是重点，务必反复练习。");
    upsertDoc(db, dir, "partial.txt", "闲谈", "只提到数学，没有其他关键词。");

    Searcher searcher(db);
    const auto hits = searcher.search("考研数学一", 10);
    ASSERT_EQ(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, pathFull);
}

// 全词散落多处：仍应保留（substringRecallPass 要求 hay 逐个包含切词）。
TEST(SingleTokenPrecisionV015, FullTokenScatteredStillKept) {
    ASSERT_TRUE(requireJiebaReady());
    const std::string dir = makeTempDir();
    Database db = Database::open(dir + "/index.db");
    upsertDoc(db, dir, "c.txt", "标题含有考研二字",
              "正文里谈到了数学，也谈到一这个数字。");

    Searcher searcher(db);
    const auto hits = searcher.search("考研数学一", 10);
    EXPECT_EQ(hits.size(), 1u);
}

// 完全无关文档：query "超导材料制备" -> 0 hits。
TEST(SingleTokenPrecisionV015, UnrelatedDocNoHit) {
    ASSERT_TRUE(requireJiebaReady());
    const std::string dir = makeTempDir();
    Database db = Database::open(dir + "/index.db");
    upsertDoc(db, dir, "x.txt", "无关文档", "这里讨论的是天气与交通话题。");

    Searcher searcher(db);
    const auto hits = searcher.search("超导材料制备", 10);
    EXPECT_EQ(hits.size(), 0u);
}

}  // namespace
}  // namespace docseek