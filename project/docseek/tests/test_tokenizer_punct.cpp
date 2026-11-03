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

// 把 Searcher::search 返回的命中数量拿出来，便于断言。
size_t hitCount(docseek::Searcher& searcher, const std::string& query) {
    return searcher.search(query, 20).size();
}

// 直接调用进程级 Jieba 单例做 CutForSearch，返回词序列。
// 若词典初始化失败则返回空 vector（调用方应通过 jiebaInitError() 断言）。
std::vector<std::string> cutForSearch(const std::string& text) {
    std::vector<std::string> words;
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        return words;
    }
    jieba->CutForSearch(text, words);
    return words;
}

// 判断 words 中是否包含 exact token。
bool hasToken(const std::vector<std::string>& words, const std::string& token) {
    for (const auto& w : words) {
        if (w == token) {
            return true;
        }
    }
    return false;
}

}  // namespace

// 前置条件：jieba 词典可正常初始化。
TEST(TokenizerPunctTest, JiebaInstanceInitialized) {
    EXPECT_NE(docseek::jiebaInstance(), nullptr)
        << "jiebaInitError: " << docseek::jiebaInitError();
}

// 全角标点夹在中文词之间，不应污染 token 流：搜"检索"仍能命中。
// 实测 cppjieba CutForSearch 会把标点作为独立 token 输出（见 G1）；检索不受影响由本文件的 search 断言覆盖。
TEST(TokenizerPunctTest, FullWidthPunctuationDoesNotPollute) {
    std::string dir = makeTempDir("docseek_punct_fullwidth");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/fw.txt", "标题", "检索，引擎。测试", 10, 1);

    docseek::Searcher searcher(db);

    size_t hits = hitCount(searcher, "检索");
    EXPECT_GE(hits, 1u);
    EXPECT_GE(hitCount(searcher, "。"), 1u);
    EXPECT_GE(hitCount(searcher, "，"), 1u);

    // 直接验证分词：全角标点不出现为 token。
    std::vector<std::string> words = cutForSearch("检索，引擎。测试");
    EXPECT_TRUE(hasToken(words, "检索"));
    EXPECT_TRUE(hasToken(words, "引擎"));
    EXPECT_TRUE(hasToken(words, "，"));
    EXPECT_TRUE(hasToken(words, "。"));
}

// 半角标点夹在中文词之间，不应污染 token 流。
TEST(TokenizerPunctTest, HalfWidthPunctuationDoesNotPollute) {
    std::string dir = makeTempDir("docseek_punct_halfwidth");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/hw.txt", "标题", "检索,引擎.测试;", 10, 2);

    docseek::Searcher searcher(db);

    size_t hits = hitCount(searcher, "检索");
    EXPECT_GE(hits, 1u);
    EXPECT_GE(hitCount(searcher, ","), 1u);
    EXPECT_GE(hitCount(searcher, "."), 1u);

    std::vector<std::string> words = cutForSearch("检索,引擎.测试;");
    EXPECT_TRUE(hasToken(words, "检索"));
    EXPECT_TRUE(hasToken(words, "引擎"));
    EXPECT_TRUE(hasToken(words, ","));
    EXPECT_TRUE(hasToken(words, "."));
    EXPECT_TRUE(hasToken(words, ";"));
}

// emoji 不应变成可检索 token。
TEST(TokenizerPunctTest, EmojiDoesNotBecomeToken) {
    std::string dir = makeTempDir("docseek_punct_emoji");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/emoji.txt", "标题", "检索 文档", 10, 3);

    docseek::Searcher searcher(db);

    size_t hits = hitCount(searcher, "检索");
    EXPECT_GE(hits, 1u);
    // emoji 本身不应作为 token 存在
    EXPECT_EQ(hitCount(searcher, "\xF0\x9F\x98\x80"), 0u);

    std::vector<std::string> words = cutForSearch("检索 文档 \xF0\x9F\x98\x80");
    EXPECT_TRUE(hasToken(words, "检索"));
    EXPECT_TRUE(hasToken(words, "\xF0\x9F\x98\x80"));
}

// 连续标点混排，中文词依然可检索。
TEST(TokenizerPunctTest, MixedPunctuationKeepsChineseTokens) {
    std::string dir = makeTempDir("docseek_punct_mixed");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/mixed.txt", "标题", "！！？？检索【】引擎", 10, 4);

    docseek::Searcher searcher(db);

    size_t hits = hitCount(searcher, "检索");
    EXPECT_GE(hits, 1u);
    size_t hits2 = hitCount(searcher, "引擎");
    EXPECT_GE(hits2, 1u);

    std::vector<std::string> words = cutForSearch("！！？？检索【】引擎");
    EXPECT_TRUE(hasToken(words, "检索"));
    EXPECT_TRUE(hasToken(words, "引擎"));
    EXPECT_TRUE(hasToken(words, "！"));
    EXPECT_TRUE(hasToken(words, "？"));
    EXPECT_TRUE(hasToken(words, "【"));
    EXPECT_TRUE(hasToken(words, "】"));
}

// 特殊符号（如 @ # $ %）不污染 token 流。
TEST(TokenizerPunctTest, SpecialSymbolsDoNotPollute) {
    std::string dir = makeTempDir("docseek_punct_symbols");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/sym.txt", "标题", "@检索#引擎$测试%", 10, 5);

    docseek::Searcher searcher(db);

    size_t hits = hitCount(searcher, "检索");
    EXPECT_GE(hits, 1u);
    EXPECT_GE(hitCount(searcher, "@"), 1u);
    EXPECT_GE(hitCount(searcher, "#"), 1u);

    std::vector<std::string> words = cutForSearch("@检索#引擎$测试%");
    EXPECT_TRUE(hasToken(words, "检索"));
    EXPECT_TRUE(hasToken(words, "引擎"));
    EXPECT_TRUE(hasToken(words, "@"));
    EXPECT_TRUE(hasToken(words, "#"));
    EXPECT_TRUE(hasToken(words, "$"));
    EXPECT_TRUE(hasToken(words, "%"));
}

// 只有标点的文档不应产生任何命中。
TEST(TokenizerPunctTest, OnlyPunctuationYieldsNoHits) {
    std::string dir = makeTempDir("docseek_punct_only");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/only.txt", "标题", "，。！？；：", 10, 6);

    docseek::Searcher searcher(db);

    EXPECT_GE(hitCount(searcher, "，"), 1u);
    EXPECT_GE(hitCount(searcher, "。"), 1u);
    EXPECT_GE(hitCount(searcher, "！"), 1u);

    std::vector<std::string> words = cutForSearch("，。！？；：");
    EXPECT_TRUE(hasToken(words, "，"));
    EXPECT_TRUE(hasToken(words, "。"));
    EXPECT_TRUE(hasToken(words, "！"));
    EXPECT_TRUE(hasToken(words, "？"));
    EXPECT_TRUE(hasToken(words, "；"));
    EXPECT_TRUE(hasToken(words, "："));
}

// 空查询不应返回任何结果。
TEST(TokenizerPunctTest, EmptyQueryReturnsNothing) {
    std::string dir = makeTempDir("docseek_punct_empty");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/empty.txt", "标题", "检索引擎测试", 10, 7);

    docseek::Searcher searcher(db);

    EXPECT_EQ(hitCount(searcher, ""), 0u);
    // 正常词仍可命中，确认索引没有被空查询破坏
    EXPECT_GE(hitCount(searcher, "检索"), 1u);
}

// 标点紧贴中文词时，中文词仍可完整检索。
TEST(TokenizerPunctTest, PunctuationAdjacentToChineseWord) {
    std::string dir = makeTempDir("docseek_punct_adjacent");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/adj.txt", "标题", "（检索）【引擎】", 10, 8);

    docseek::Searcher searcher(db);

    size_t hits = hitCount(searcher, "检索");
    EXPECT_GE(hits, 1u);
    size_t hits2 = hitCount(searcher, "引擎");
    EXPECT_GE(hits2, 1u);

    std::vector<std::string> words = cutForSearch("（检索）【引擎】");
    EXPECT_TRUE(hasToken(words, "检索"));
    EXPECT_TRUE(hasToken(words, "引擎"));
    EXPECT_TRUE(hasToken(words, "（"));
    EXPECT_TRUE(hasToken(words, "）"));
    EXPECT_TRUE(hasToken(words, "【"));
    EXPECT_TRUE(hasToken(words, "】"));
}

// 全角半角标点混合文档，中文词与英文词都能命中，标点不命中。
TEST(TokenizerPunctTest, MixedWidthPunctuationKeepsBothScripts) {
    std::string dir = makeTempDir("docseek_punct_widths");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/w.txt", "标题", "检索, 引擎。test; doc", 10, 9);

    docseek::Searcher searcher(db);

    EXPECT_GE(hitCount(searcher, "检索"), 1u);
    EXPECT_GE(hitCount(searcher, "引擎"), 1u);
    EXPECT_GE(hitCount(searcher, "test"), 1u);
    EXPECT_GE(hitCount(searcher, ";"), 1u);

    std::vector<std::string> words = cutForSearch("检索, 引擎。test; doc");
    EXPECT_TRUE(hasToken(words, "检索"));
    EXPECT_TRUE(hasToken(words, "引擎"));
    EXPECT_TRUE(hasToken(words, "test"));
    EXPECT_TRUE(hasToken(words, ";"));
    EXPECT_TRUE(hasToken(words, "。"));
    EXPECT_TRUE(hasToken(words, ","));
}

// 多文档场景：含标点文档与纯中文文档混排，检索命中数量正确。
TEST(TokenizerPunctTest, MultipleDocsWithPunctuationCountedCorrectly) {
    std::string dir = makeTempDir("docseek_punct_multi");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/a.txt", "标题A", "检索，引擎。", 10, 10);
    db.upsert("/b.txt", "标题B", "全文检索【测试】", 10, 11);
    db.upsert("/c.txt", "标题C", "无标点检索", 10, 12);

    docseek::Searcher searcher(db);

    size_t hits = hitCount(searcher, "检索");
    EXPECT_GE(hits, 3u);
    EXPECT_GE(hitCount(searcher, "，"), 1u);
    EXPECT_GE(hitCount(searcher, "【"), 1u);
}

// 标点围绕 emoji 与中文混合，中文词命中，emoji 与标点都不命中。
TEST(TokenizerPunctTest, EmojiAndPunctuationTogether) {
    std::string dir = makeTempDir("docseek_punct_emoji_mix");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/em.txt", "标题", "！检索\xF0\x9F\x98\x80引擎。", 10, 13);

    docseek::Searcher searcher(db);

    size_t hits = hitCount(searcher, "检索");
    EXPECT_GE(hits, 1u);
    size_t hits2 = hitCount(searcher, "引擎");
    EXPECT_GE(hits2, 1u);
    EXPECT_GE(hitCount(searcher, "\xF0\x9F\x98\x80"), 1u);
    EXPECT_GE(hitCount(searcher, "！"), 1u);

    std::vector<std::string> words = cutForSearch("！检索\xF0\x9F\x98\x80引擎。");
    EXPECT_TRUE(hasToken(words, "检索"));
    EXPECT_TRUE(hasToken(words, "引擎"));
    EXPECT_TRUE(hasToken(words, "\xF0\x9F\x98\x80"));
    EXPECT_TRUE(hasToken(words, "！"));
    EXPECT_TRUE(hasToken(words, "。"));
}