#include <gtest/gtest.h>

#include "docseek/bigram_tokenizer.h"

#include <sqlite3.h>

#include <algorithm>
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

// 判断 token 列表中是否包含指定 token
bool containsToken(const std::vector<std::string>& tokens, const std::string& want) {
    return std::find(tokens.begin(), tokens.end(), want) != tokens.end();
}

// 找到指定 token 在列表中的下标，找不到返回 -1
int indexOfToken(const std::vector<std::string>& tokens, const std::string& want) {
    for (std::size_t i = 0; i < tokens.size(); ++i) {
        if (tokens[i] == want) {
            return static_cast<int>(i);
        }
    }
    return -1;
}

}  // namespace

// 基本 bigram：全文检索 → [全文, 文检, 检索]（顺序一致）
TEST(BigramTokenizerTest, CutFullTextSearchOrdered) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("全文检索");
    ASSERT_EQ(tokens.size(), 3u);
    EXPECT_EQ(tokens[0], "全文");
    EXPECT_EQ(tokens[1], "文检");
    EXPECT_EQ(tokens[2], "检索");
}

// 基本 bigram：搜索引擎 → [搜索, 索引, 引擎]
TEST(BigramTokenizerTest, CutSearchEngineOrdered) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("搜索引擎");
    ASSERT_EQ(tokens.size(), 3u);
    EXPECT_EQ(tokens[0], "搜索");
    EXPECT_EQ(tokens[1], "索引");
    EXPECT_EQ(tokens[2], "引擎");
}

// 奇数字尾：这是书 含 这是、是书，且不含落单的停用词「是」
TEST(BigramTokenizerTest, CutOddLengthTailDropsLoneStopword) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("这是书");
    // 双停用字 bigram「这是」被过滤，保留「是书」与非停用奇数尾「书」
    EXPECT_FALSE(containsToken(tokens, "这是"));
    EXPECT_TRUE(containsToken(tokens, "是书"));
    EXPECT_TRUE(containsToken(tokens, "书"));
    EXPECT_FALSE(containsToken(tokens, "是"));
}

// 单字停用词「的」被过滤
TEST(BigramTokenizerTest, SingleStopwordDeFiltered) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("的");
    EXPECT_TRUE(tokens.empty());
}

// 单字停用词「了」被过滤
TEST(BigramTokenizerTest, SingleStopwordLeFiltered) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("了");
    EXPECT_TRUE(tokens.empty());
}

// 单字停用词「是」被过滤
TEST(BigramTokenizerTest, SingleStopwordShiFiltered) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("是");
    EXPECT_TRUE(tokens.empty());
}

// 单字停用词「在」被过滤
TEST(BigramTokenizerTest, SingleStopwordZaiFiltered) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("在");
    EXPECT_TRUE(tokens.empty());
}

// bigram 双停用词「是在」被过滤
TEST(BigramTokenizerTest, BigramStopwordShiZaiFiltered) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("是在");
    EXPECT_FALSE(containsToken(tokens, "是在"));
}

// 数字保护：价格100.5% 含 token "100.5%"
TEST(BigramTokenizerTest, NumberProtectionPercent) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("价格100.5%");
    EXPECT_TRUE(containsToken(tokens, "100.5%"));
}

// 数字保护：2026年 含 "2026"
TEST(BigramTokenizerTest, NumberProtectionYear) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("2026年");
    EXPECT_TRUE(containsToken(tokens, "2026"));
}

// 数字保护：1,000 含 "1,000"
TEST(BigramTokenizerTest, NumberProtectionThousandSeparator) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("1,000");
    EXPECT_TRUE(containsToken(tokens, "1,000"));
}

// 专名附加：杭州市 含 "杭州市" 以及 bigram
TEST(BigramTokenizerTest, ProperNounHangzhou) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("杭州市");
    EXPECT_TRUE(containsToken(tokens, "杭州市"));
    EXPECT_TRUE(containsToken(tokens, "杭州"));
    EXPECT_TRUE(containsToken(tokens, "州市"));
}

// 专名附加：王小明 含 "王小明" 以及 bigram
TEST(BigramTokenizerTest, ProperNounWangXiaoming) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("王小明");
    EXPECT_TRUE(containsToken(tokens, "王小明"));
    EXPECT_TRUE(containsToken(tokens, "王小"));
    EXPECT_TRUE(containsToken(tokens, "小明"));
}

// 专名附加只增不减：杭州市 的 bigram 仍全在，且专名 token 在末尾附近
TEST(BigramTokenizerTest, ProperNounIsAdditiveOnly) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("杭州市");
    int bigramIdx = indexOfToken(tokens, "杭州");
    int properIdx = indexOfToken(tokens, "杭州市");
    ASSERT_GE(bigramIdx, 0);
    ASSERT_GE(properIdx, 0);
    // bigram 先出现，专名附加 token 不替换 bigram
    EXPECT_LT(bigramIdx, properIdx);
}

// 中英混排：docseek全文检索工具 首 token 为 "docseek"（小写）
TEST(BigramTokenizerTest, MixedAsciiCjkFirstToken) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("docseek全文检索工具");
    ASSERT_FALSE(tokens.empty());
    EXPECT_EQ(tokens[0], "docseek");
    EXPECT_TRUE(containsToken(tokens, "全文"));
    EXPECT_TRUE(containsToken(tokens, "检索"));
    EXPECT_TRUE(containsToken(tokens, "工具"));
}

// 大小写：DocSeek → "docseek"
TEST(BigramTokenizerTest, AsciiLowercased) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("DocSeek");
    ASSERT_EQ(tokens.size(), 1u);
    EXPECT_EQ(tokens[0], "docseek");
}

// 空输入 → 空 vector
TEST(BigramTokenizerTest, EmptyInputReturnsEmpty) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("");
    EXPECT_TRUE(tokens.empty());
}

// 纯标点 → 空 vector
TEST(BigramTokenizerTest, PurePunctuationReturnsEmpty) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("，。！？");
    EXPECT_TRUE(tokens.empty());
}

// 纯空白 → 空 vector
TEST(BigramTokenizerTest, PureWhitespaceReturnsEmpty) {
    std::vector<std::string> tokens = docseek::bigramCutForSearch("   \t\n  ");
    EXPECT_TRUE(tokens.empty());
}

// 非法 UTF-8 字节 → 不崩溃
TEST(BigramTokenizerTest, InvalidUtf8DoesNotCrash) {
    std::string bad = "\xff\xfe";
    std::vector<std::string> tokens = docseek::bigramCutForSearch(bad);
    // 仅要求不崩溃，长度可为 0 或若干
    EXPECT_LE(tokens.size(), bad.size());
}

// 超长输入（10 万字「检索」重复）耗时 < 2 秒
TEST(BigramTokenizerTest, VeryLongInputCompletesQuickly) {
    std::string text;
    text.reserve(200000);
    for (int i = 0; i < 100000; ++i) {
        text += "检索";
    }
    auto start = std::chrono::steady_clock::now();
    std::vector<std::string> tokens = docseek::bigramCutForSearch(text);
    auto end = std::chrono::steady_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();
    EXPECT_LT(ms, 2000);
    EXPECT_FALSE(tokens.empty());
}

// decodeUtf8：检索 得到两个正确码点
TEST(BigramTokenizerTest, DecodeUtf8Chinese) {
    std::vector<uint32_t> cps = docseek::bigram_detail::decodeUtf8("检索");
    ASSERT_EQ(cps.size(), 2u);
    EXPECT_EQ(cps[0], 0x68C0u);  // 检
    EXPECT_EQ(cps[1], 0x7D22u);  // 索
}

// decodeUtf8/encodeUtf8 往返：检索
TEST(BigramTokenizerTest, EncodeDecodeRoundTrip) {
    const std::string original = "检索";
    std::vector<uint32_t> cps = docseek::bigram_detail::decodeUtf8(original);
    ASSERT_EQ(cps.size(), 2u);
    std::string rebuilt;
    for (uint32_t cp : cps) {
        rebuilt += docseek::bigram_detail::encodeUtf8(cp);
    }
    EXPECT_EQ(rebuilt, original);
}

// encodeUtf8：U+4E2D 编码为中
TEST(BigramTokenizerTest, EncodeUtf8Cjk) {
    EXPECT_EQ(docseek::bigram_detail::encodeUtf8(0x4E2Du), "中");
}

// isCjk：'a' 为 false，U+4E2D 为 true
TEST(BigramTokenizerTest, IsCjkClassification) {
    EXPECT_FALSE(docseek::bigram_detail::isCjk(static_cast<uint32_t>('a')));
    EXPECT_TRUE(docseek::bigram_detail::isCjk(0x4E2Du));
}

// isAsciiAlnum：字母/数字为 true，标点为 false
TEST(BigramTokenizerTest, IsAsciiAlnumClassification) {
    EXPECT_TRUE(docseek::bigram_detail::isAsciiAlnum(static_cast<uint32_t>('a')));
    EXPECT_TRUE(docseek::bigram_detail::isAsciiAlnum(static_cast<uint32_t>('Z')));
    EXPECT_TRUE(docseek::bigram_detail::isAsciiAlnum(static_cast<uint32_t>('0')));
    EXPECT_FALSE(docseek::bigram_detail::isAsciiAlnum(static_cast<uint32_t>('.')));
}

// isCjkStopword：是 为 true，检 为 false
TEST(BigramTokenizerTest, IsCjkStopwordClassification) {
    EXPECT_TRUE(docseek::bigram_detail::isCjkStopword(0x662Fu));  // 是
    EXPECT_FALSE(docseek::bigram_detail::isCjkStopword(0x68C0u));  // 检
}

// cutCjkRun：三字 杭州市 产生两个 bigram
TEST(BigramTokenizerTest, CutCjkRunThreeChars) {
    std::vector<uint32_t> cps = docseek::bigram_detail::decodeUtf8("杭州市");
    std::vector<std::string> out = docseek::bigram_detail::cutCjkRun(cps);
    ASSERT_GE(out.size(), 2u);
    EXPECT_EQ(out[0], "杭州");
    EXPECT_EQ(out[1], "州市");
}

// FTS5 端到端：注册 + MATCH 检索 查到 1 行
TEST(BigramTokenizerTest, Fts5EndToEndMatchJianSuo) {
    sqlite3* db = nullptr;
    ASSERT_EQ(sqlite3_open(":memory:", &db), SQLITE_OK);
    ASSERT_NE(db, nullptr);
    ASSERT_EQ(docseek::registerBigramTokenizer(db), SQLITE_OK);

    const char* createSql =
        "CREATE VIRTUAL TABLE t USING fts5(x, tokenize='bigram')";
    char* errmsg = nullptr;
    ASSERT_EQ(sqlite3_exec(db, createSql, nullptr, nullptr, &errmsg), SQLITE_OK)
        << (errmsg ? errmsg : "");

    const char* insertSql =
        "INSERT INTO t(x) VALUES ('全文检索引擎测试')";
    ASSERT_EQ(sqlite3_exec(db, insertSql, nullptr, nullptr, &errmsg), SQLITE_OK)
        << (errmsg ? errmsg : "");

    sqlite3_stmt* stmt = nullptr;
    const char* querySql = "SELECT count(*) FROM t WHERE t MATCH '检索'";
    ASSERT_EQ(sqlite3_prepare_v2(db, querySql, -1, &stmt, nullptr), SQLITE_OK);
    ASSERT_EQ(sqlite3_step(stmt), SQLITE_ROW);
    EXPECT_EQ(sqlite3_column_int(stmt, 0), 1);
    sqlite3_finalize(stmt);
    sqlite3_close(db);
}

// FTS5 端到端：MATCH '全文检索' 查到 1 行
TEST(BigramTokenizerTest, Fts5EndToEndMatchFullText) {
    sqlite3* db = nullptr;
    ASSERT_EQ(sqlite3_open(":memory:", &db), SQLITE_OK);
    ASSERT_EQ(docseek::registerBigramTokenizer(db), SQLITE_OK);

    char* errmsg = nullptr;
    ASSERT_EQ(sqlite3_exec(db,
                           "CREATE VIRTUAL TABLE t USING fts5(x, tokenize='bigram')",
                           nullptr, nullptr, &errmsg),
              SQLITE_OK)
        << (errmsg ? errmsg : "");
    ASSERT_EQ(sqlite3_exec(db,
                           "INSERT INTO t(x) VALUES ('全文检索引擎测试')",
                           nullptr, nullptr, &errmsg),
              SQLITE_OK)
        << (errmsg ? errmsg : "");

    sqlite3_stmt* stmt = nullptr;
    ASSERT_EQ(sqlite3_prepare_v2(db,
                                 "SELECT count(*) FROM t WHERE t MATCH '全文检索'",
                                 -1, &stmt, nullptr),
              SQLITE_OK);
    ASSERT_EQ(sqlite3_step(stmt), SQLITE_ROW);
    EXPECT_EQ(sqlite3_column_int(stmt, 0), 1);
    sqlite3_finalize(stmt);
    sqlite3_close(db);
}

// FTS5 端到端：MATCH '不存在xyz' 查到 0 行
TEST(BigramTokenizerTest, Fts5EndToEndNoMatch) {
    sqlite3* db = nullptr;
    ASSERT_EQ(sqlite3_open(":memory:", &db), SQLITE_OK);
    ASSERT_EQ(docseek::registerBigramTokenizer(db), SQLITE_OK);

    char* errmsg = nullptr;
    ASSERT_EQ(sqlite3_exec(db,
                           "CREATE VIRTUAL TABLE t USING fts5(x, tokenize='bigram')",
                           nullptr, nullptr, &errmsg),
              SQLITE_OK)
        << (errmsg ? errmsg : "");
    ASSERT_EQ(sqlite3_exec(db,
                           "INSERT INTO t(x) VALUES ('全文检索引擎测试')",
                           nullptr, nullptr, &errmsg),
              SQLITE_OK)
        << (errmsg ? errmsg : "");

    sqlite3_stmt* stmt = nullptr;
    ASSERT_EQ(sqlite3_prepare_v2(db,
                                 "SELECT count(*) FROM t WHERE t MATCH '不存在xyz'",
                                 -1, &stmt, nullptr),
              SQLITE_OK);
    ASSERT_EQ(sqlite3_step(stmt), SQLITE_ROW);
    EXPECT_EQ(sqlite3_column_int(stmt, 0), 0);
    sqlite3_finalize(stmt);
    sqlite3_close(db);
}

// 注册幂等：同一连接调两次 registerBigramTokenizer 不崩且返回 SQLITE_OK
TEST(BigramTokenizerTest, RegisterTwiceIsIdempotent) {
    sqlite3* db = nullptr;
    ASSERT_EQ(sqlite3_open(":memory:", &db), SQLITE_OK);
    EXPECT_EQ(docseek::registerBigramTokenizer(db), SQLITE_OK);
    EXPECT_EQ(docseek::registerBigramTokenizer(db), SQLITE_OK);
    sqlite3_close(db);
}

// 注册后仍可正常建表并写入（幂等后状态一致）
TEST(BigramTokenizerTest, RegisterTwiceThenUse) {
    sqlite3* db = nullptr;
    ASSERT_EQ(sqlite3_open(":memory:", &db), SQLITE_OK);
    ASSERT_EQ(docseek::registerBigramTokenizer(db), SQLITE_OK);
    ASSERT_EQ(docseek::registerBigramTokenizer(db), SQLITE_OK);

    char* errmsg = nullptr;
    ASSERT_EQ(sqlite3_exec(db,
                           "CREATE VIRTUAL TABLE t USING fts5(x, tokenize='bigram')",
                           nullptr, nullptr, &errmsg),
              SQLITE_OK)
        << (errmsg ? errmsg : "");
    ASSERT_EQ(sqlite3_exec(db,
                           "INSERT INTO t(x) VALUES ('搜索引擎测试')",
                           nullptr, nullptr, &errmsg),
              SQLITE_OK)
        << (errmsg ? errmsg : "");

    sqlite3_stmt* stmt = nullptr;
    ASSERT_EQ(sqlite3_prepare_v2(db,
                                 "SELECT count(*) FROM t WHERE t MATCH '搜索'",
                                 -1, &stmt, nullptr),
              SQLITE_OK);
    ASSERT_EQ(sqlite3_step(stmt), SQLITE_ROW);
    EXPECT_EQ(sqlite3_column_int(stmt, 0), 1);
    sqlite3_finalize(stmt);
    sqlite3_close(db);
}

// 临时目录 helper 可正常工作（相对 build/test-tmp，不使用 /tmp）
TEST(BigramTokenizerTest, MakeTempDirUnderBuild) {
    std::string dir = makeTempDir("bigram_tokenizer");
    EXPECT_TRUE(std::filesystem::exists(dir));
    std::filesystem::remove_all(dir);
}

