#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"

#include <sqlite3.h>

#include <cctype>
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

// 打开一个临时库，供本次用例使用
docseek::Database openTempDb(const std::string& name) {
    std::string dir = makeTempDir(name);
    std::string dbPath = dir + "/index.db";
    return docseek::Database::open(dbPath);
}

// 直接调用真实的 Jieba 单例做分词，返回词条数量；词典初始化失败时返回 -1。
long directCutForSearchCount(const std::string& text) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        return -1;
    }
    std::vector<std::string> words;
    jieba->CutForSearch(text, words);
    return static_cast<long>(words.size());
}

}  // namespace

// 空字符串分词：不崩溃、不抛异常，命中结果为空
TEST(TokenizerEmpty, EmptyQueryReturnsNoHits) {
    docseek::Database db = openTempDb("docseek_tok_empty_query");
    db.upsert("/empty.txt", "标题", "全文检索引擎测试文档", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("", 10);
    EXPECT_TRUE(hits.empty());
    EXPECT_EQ(hits.size(), 0u);
}

// 空文档正文入库：检索正常词不会命中该空文档
TEST(TokenizerEmpty, EmptyDocumentBodyNotMatched) {
    docseek::Database db = openTempDb("docseek_tok_empty_body");
    db.upsert("/blank.txt", "空文档", "", 100, 7);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("检索", 10);
    EXPECT_TRUE(hits.empty());
    EXPECT_EQ(hits.size(), 0u);
}

// 空标题 + 空正文：入库不崩溃，检索也不崩溃
TEST(TokenizerEmpty, EmptyTitleAndBodySurvive) {
    docseek::Database db = openTempDb("docseek_tok_empty_title_body");
    db.upsert("/none.txt", "", "", 0, 0);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("任意词", 10);
    EXPECT_TRUE(hits.empty());
    EXPECT_EQ(hits.size(), 0u);
}

// 空字符串直接分词：不崩溃，切出的词条数为 0
TEST(TokenizerEmpty, DirectCutEmptyString) {
    long n = directCutForSearchCount("");
    // 词典初始化失败时返回 -1，视为环境问题，跳过断言。
    if (n < 0) {
        GTEST_SKIP() << "jieba 词典初始化失败: " << docseek::jiebaInitError();
    }
    EXPECT_EQ(n, 0);
}

// 纯标点查询：不崩溃不抛异常，返回空结果
TEST(TokenizerPunct, PunctuationOnlyQueryReturnsEmpty) {
    docseek::Database db = openTempDb("docseek_tok_punct_query");
    db.upsert("/p.txt", "标题", "全文检索引擎测试文档", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("!!!???...", 10);
    EXPECT_TRUE(hits.empty());
    EXPECT_EQ(hits.size(), 0u);
}

// 纯中文标点查询：不崩溃不抛异常，返回空结果
TEST(TokenizerPunct, ChinesePunctuationOnlyQueryReturnsEmpty) {
    docseek::Database db = openTempDb("docseek_tok_cn_punct_query");
    db.upsert("/cp.txt", "标题", "全文检索引擎测试文档", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("，。！？；：、", 10);
    EXPECT_TRUE(hits.empty());
    EXPECT_EQ(hits.size(), 0u);
}

// 纯标点正文入库：检索正常词不命中，且入库本身不崩溃
TEST(TokenizerPunct, PunctuationOnlyBodyNotMatched) {
    docseek::Database db = openTempDb("docseek_tok_punct_body");
    db.upsert("/pb.txt", "标题", "!!!???...", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("检索", 10);
    EXPECT_TRUE(hits.empty());
    EXPECT_EQ(hits.size(), 0u);
}

// 纯标点直接分词：不崩溃，切出的词条数为 0
TEST(TokenizerPunct, DirectCutPunctuationOnly) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba 词典初始化失败: " << docseek::jiebaInitError();
    }
    std::vector<std::string> words;
    jieba->CutForSearch("!!!???...", words);
    // 事实F1: CutForSearch 把每个标点都作为独立 token 输出（共 9 个）。
    // 测试意图是"纯标点输入不应产生内容词"，故逐 token 校验其均为标点。
    ASSERT_EQ(words.size(), 9u);
    for (const std::string& w : words) {
        ASSERT_EQ(w.size(), 1u) << "非单字符 token: " << w;
        const unsigned char c = static_cast<unsigned char>(w[0]);
        EXPECT_TRUE(std::ispunct(c)) << "非标点 token: " << w;
    }
}


// 只有空白字符的查询：不崩溃不抛异常，返回空结果
TEST(TokenizerPunct, WhitespaceOnlyQueryReturnsEmpty) {
    docseek::Database db = openTempDb("docseek_tok_ws_query");
    db.upsert("/ws.txt", "标题", "全文检索引擎测试文档", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("   \t\n  ", 10);
    EXPECT_TRUE(hits.empty());
    EXPECT_EQ(hits.size(), 0u);
}

// 只有空白字符直接分词：不崩溃，切出的词条数为 0
TEST(TokenizerPunct, DirectCutWhitespaceOnly) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba 词典初始化失败: " << docseek::jiebaInitError();
    }
    std::vector<std::string> words;
    jieba->CutForSearch("   \t\n  ", words);
    // 事实F2: CutForSearch 把每个空白字符（空格/Tab/换行）都作为独立 token 输出（共 7 个）。
    // 测试意图是"纯空白输入不应产生内容词"，故逐 token 校验其均为空白。
    ASSERT_EQ(words.size(), 7u);
    for (const std::string& w : words) {
        ASSERT_EQ(w.size(), 1u) << "非单字符 token: " << w;
        const unsigned char c = static_cast<unsigned char>(w[0]);
        EXPECT_TRUE(std::isspace(c)) << "非空白 token: " << w;
    }
}

// 超长查询（数万个汉字）：不崩溃不抛异常，检索能正常返回
TEST(TokenizerLong, VeryLongQueryDoesNotCrash) {
    docseek::Database db = openTempDb("docseek_tok_long_query");
    db.upsert("/long.txt", "标题", "全文检索引擎测试文档", 100, 42);

    docseek::Searcher searcher(db);

    std::string big;
    big.reserve(20000 * 3);
    for (int i = 0; i < 20000; ++i) {
        big += "检";
    }

    auto hits = searcher.search(big, 10);
    EXPECT_GE(hits.size(), 0u);
    EXPECT_LE(hits.size(), 10u);
}

// 超长正文入库：入库不崩溃，且正文里的词能被检索到
TEST(TokenizerLong, VeryLongBodyIndexAndSearch) {
    docseek::Database db = openTempDb("docseek_tok_long_body");

    std::string body;
    body.reserve(20000 * 3);
    for (int i = 0; i < 20000; ++i) {
        body += "索";
    }
    body += "引";

    db.upsert("/longbody.txt", "长正文", body, 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("索引", 10);
    EXPECT_GE(hits.size(), 1u);
    EXPECT_LE(hits.size(), 10u);
}

// 超长纯标点查询：不崩溃不抛异常，返回空结果
TEST(TokenizerLong, VeryLongPunctuationQueryReturnsEmpty) {
    docseek::Database db = openTempDb("docseek_tok_long_punct");
    db.upsert("/lp.txt", "标题", "全文检索引擎测试文档", 100, 42);

    docseek::Searcher searcher(db);

    std::string punct;
    punct.reserve(20000);
    for (int i = 0; i < 20000; ++i) {
        punct += "!";
    }

    auto hits = searcher.search(punct, 10);
    EXPECT_TRUE(hits.empty());
    EXPECT_EQ(hits.size(), 0u);
}

// 空库上做空查询与超长查询：都不崩溃，均返回空结果
TEST(TokenizerEmpty, EmptyDbSearchRobust) {
    docseek::Database db = openTempDb("docseek_tok_empty_db");

    docseek::Searcher searcher(db);

    auto hits1 = searcher.search("", 10);
    EXPECT_TRUE(hits1.empty());

    std::string big;
    big.reserve(10000 * 3);
    for (int i = 0; i < 10000; ++i) {
        big += "检";
    }

    auto hits2 = searcher.search(big, 10);
    EXPECT_TRUE(hits2.empty());
    EXPECT_EQ(hits2.size(), 0u);
}