#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"

#include <sqlite3.h>

#include <chrono>
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

// 构造一段重复的中文文本，总字节数大约为 targetBytes。
// 用固定句子拼接，保证每次内容可复现。
std::string makeChineseText(std::size_t targetBytes) {
    static const char* kSentence =
        "全文检索引擎支持中文分词和倒排索引构建以及快速检索排序。";
    std::string text;
    text.reserve(targetBytes + 256);
    while (text.size() < targetBytes) {
        text += kSentence;
    }
    return text;
}

// 统计 UTF-8 文本的字符个数（近似按非续字节计数）。
std::size_t countUtf8Chars(const std::string& s) {
    std::size_t n = 0;
    for (unsigned char c : s) {
        if ((c & 0xC0) != 0x80) {
            ++n;
        }
    }
    return n;
}

// 直接调用进程级 Jieba 单例做一次分词，返回切出的词数。
// 若词典未初始化成功（jiebaInstance() 返回 nullptr），返回 0 并打印错误。
std::size_t tokenizeAndCountDirect(const std::string& text) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        ADD_FAILURE() << "jiebaInstance() returned nullptr: "
                      << docseek::jiebaInitError();
        return 0;
    }
    std::vector<std::string> words;
    jieba->CutForSearch(text, words);
    return words.size();
}

// 端到端：把文本作为文档正文写入索引，再用一个必然出现在正文里的词去检索。
// 返回检索命中数。
std::size_t tokenizeAndCount(docseek::Database& db,
                             docseek::Searcher& searcher,
                             const std::string& docPath,
                             const std::string& text) {
    db.upsert(docPath, "标题", text, static_cast<int>(text.size()), 1);
    auto hits = searcher.search("检索", 10);
    return hits.size();
}

}  // namespace

// 直接调用 jiebaInstance() 对 1MB 中文文本分词，耗时上限断言。
TEST(TokenizerPerf, DirectOneMegabyteChineseTokenizeUnderLimit) {
    std::string text = makeChineseText(1024 * 1024);
    ASSERT_GE(text.size(), 1024u * 1024u);
    std::size_t charCount = countUtf8Chars(text);
    ASSERT_GT(charCount, 100000u);

    auto start = std::chrono::steady_clock::now();
    std::size_t wordCount = tokenizeAndCountDirect(text);
    auto end = std::chrono::steady_clock::now();

    auto elapsedMs =
        std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    EXPECT_GT(wordCount, 0u);
    EXPECT_LT(elapsedMs, 20000);
}

// 直接分词 512KB 中文文本，耗时上限应明显小于 1MB 场景。
TEST(TokenizerPerf, DirectHalfMegabyteChineseTokenizeUnderLimit) {
    std::string text = makeChineseText(512 * 1024);
    ASSERT_GE(text.size(), 512u * 1024u);

    auto start = std::chrono::steady_clock::now();
    std::size_t wordCount = tokenizeAndCountDirect(text);
    auto end = std::chrono::steady_clock::now();

    auto elapsedMs =
        std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    EXPECT_GT(wordCount, 0u);
    EXPECT_LT(elapsedMs, 10000);
}

// 直接分词 256KB 中文文本，进一步收紧耗时上限。
TEST(TokenizerPerf, DirectQuarterMegabyteChineseTokenizeUnderLimit) {
    std::string text = makeChineseText(256 * 1024);
    ASSERT_GE(text.size(), 256u * 1024u);

    auto start = std::chrono::steady_clock::now();
    std::size_t wordCount = tokenizeAndCountDirect(text);
    auto end = std::chrono::steady_clock::now();

    auto elapsedMs =
        std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    EXPECT_GT(wordCount, 0u);
    EXPECT_LT(elapsedMs, 5000);
}

// 多次直接分词 1MB 文本，验证平均耗时稳定在上限内。
TEST(TokenizerPerf, DirectOneMegabyteRepeatedTokenizeAverageUnderLimit) {
    std::string text = makeChineseText(1024 * 1024);
    ASSERT_GE(text.size(), 1024u * 1024u);

    const int kRounds = 3;
    std::int64_t totalMs = 0;
    for (int i = 0; i < kRounds; ++i) {
        auto start = std::chrono::steady_clock::now();
        std::size_t wordCount = tokenizeAndCountDirect(text);
        auto end = std::chrono::steady_clock::now();
        auto elapsedMs =
            std::chrono::duration_cast<std::chrono::milliseconds>(end - start)
                .count();
        EXPECT_GT(wordCount, 0u);
        totalMs += elapsedMs;
    }

    std::int64_t avgMs = totalMs / kRounds;
    EXPECT_LT(avgMs, 20000);
}

// 端到端：1MB 中文文本建索引 + 检索，验证真实分词路径命中。
TEST(TokenizerPerf, EndToEndOneMegabyteTokenizeThenSearchHit) {
    std::string dir = makeTempDir("docseek_tokenizer_perf_search");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    docseek::Searcher searcher(db);

    std::string text = makeChineseText(1024 * 1024);
    ASSERT_GE(text.size(), 1024u * 1024u);

    auto start = std::chrono::steady_clock::now();
    db.upsert("/search_1mb.txt", "标题", text, static_cast<int>(text.size()), 7);
    auto hitsFull = searcher.search("全文检索", 10);
    auto end = std::chrono::steady_clock::now();

    auto elapsedMs =
        std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    EXPECT_GE(hitsFull.size(), 1u);
    EXPECT_LT(elapsedMs, 20000);
}

// 边界：文本刚好为空，分词与检索不应崩溃，且检索命中为 0。
TEST(TokenizerPerf, EmptyTextTokenizeNoHit) {
    std::string dir = makeTempDir("docseek_tokenizer_perf_empty");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    docseek::Searcher searcher(db);

    std::string text = "";
    ASSERT_EQ(text.size(), 0u);

    db.upsert("/empty.txt", "标题", text, 0, 1);
    auto hits = searcher.search("检索", 10);

    EXPECT_TRUE(hits.empty());
    EXPECT_EQ(text.size(), 0u);
}

// 边界：直接分词空串，词数为 0。
TEST(TokenizerPerf, DirectEmptyTextZeroWords) {
    std::size_t wordCount = tokenizeAndCountDirect("");
    EXPECT_EQ(wordCount, 0u);
}

// 边界：单个中文字，直接分词与端到端检索都要能跑通。
TEST(TokenizerPerf, SingleChineseCharTokenizeAndSearch) {
    std::string dir = makeTempDir("docseek_tokenizer_perf_single");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    docseek::Searcher searcher(db);

    std::string text = "检";
    ASSERT_EQ(countUtf8Chars(text), 1u);

    // 直接分词路径
    std::size_t directWords = tokenizeAndCountDirect(text);
    EXPECT_GT(directWords, 0u);

    // 端到端路径
    auto start = std::chrono::steady_clock::now();
    db.upsert("/single.txt", "标题", text, static_cast<int>(text.size()), 1);
    auto hits = searcher.search("检", 10);
    auto end = std::chrono::steady_clock::now();

    auto elapsedMs =
        std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    EXPECT_GE(hits.size(), 1u);
    EXPECT_LT(elapsedMs, 1000);
}

// 边界：纯 ASCII 文本混在中文分词路径里，耗时应远低于中文大文本。
TEST(TokenizerPerf, AsciiOnlyTextTokenizeFast) {
    std::string dir = makeTempDir("docseek_tokenizer_perf_ascii");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    docseek::Searcher searcher(db);

    std::string text;
    text.reserve(256 * 1024);
    while (text.size() < 256u * 1024u) {
        text += "abcdefghijklmnopqrstuvwxyz0123456789";
    }
    ASSERT_GE(text.size(), 256u * 1024u);

    auto start = std::chrono::steady_clock::now();
    db.upsert("/ascii.txt", "标题", text, static_cast<int>(text.size()), 1);
    auto hits = searcher.search("abcdefghijklmnopqrstuvwxyz0123456789", 10);
    auto end = std::chrono::steady_clock::now();

    auto elapsedMs =
        std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    EXPECT_GE(hits.size(), 1u);
    EXPECT_LT(elapsedMs, 10000);
}

// 边界：2MB 中文文本，耗时上限放宽到 40 秒，验证超长文本不卡死。
TEST(TokenizerPerf, DirectTwoMegabyteChineseTokenizeUnderLimit) {
    std::string text = makeChineseText(2 * 1024 * 1024);
    ASSERT_GE(text.size(), 2u * 1024u * 1024u);

    auto start = std::chrono::steady_clock::now();
    std::size_t wordCount = tokenizeAndCountDirect(text);
    auto end = std::chrono::steady_clock::now();

    auto elapsedMs =
        std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    EXPECT_GT(wordCount, 0u);
    EXPECT_LT(elapsedMs, 40000);
}

// 边界：构造大文本这一步本身不能太慢，保证测试基础设施可用。
TEST(TokenizerPerf, MakeChineseTextConstructionIsFast) {
    auto start = std::chrono::steady_clock::now();
    std::string text = makeChineseText(1024 * 1024);
    auto end = std::chrono::steady_clock::now();

    auto elapsedMs =
        std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    EXPECT_GE(text.size(), 1024u * 1024u);
    EXPECT_LT(elapsedMs, 2000);
}