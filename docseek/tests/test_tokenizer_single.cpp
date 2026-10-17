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

// 断言 jieba 单例可用；不可用时直接失败并给出错误信息
void requireJiebaAvailable() {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init failed: " << docseek::jiebaInitError();
}

}  // namespace

// 直接分词：单字“的”应出现在 CutForSearch 结果中
TEST(TokenizerSingleChar, DirectDeTokenized) {
    requireJiebaAvailable();
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr);

    std::vector<std::string> words;
    jieba->CutForSearch("的的的", words);

    bool found = false;
    for (const auto& w : words) {
        if (w == "的") { found = true; break; }
    }
    EXPECT_TRUE(found);
}

// 直接分词：单字“猫”应出现在 CutForSearch 结果中
TEST(TokenizerSingleChar, DirectMaoTokenized) {
    requireJiebaAvailable();
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr);

    std::vector<std::string> words;
    jieba->CutForSearch("我家养了一只猫", words);

    bool found = false;
    for (const auto& w : words) {
        if (w == "猫") { found = true; break; }
    }
    EXPECT_TRUE(found);
}

// 直接分词：单字“狗”应出现在 CutForSearch 结果中
TEST(TokenizerSingleChar, DirectGouTokenized) {
    requireJiebaAvailable();
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr);

    std::vector<std::string> words;
    jieba->CutForSearch("院子里跑着一条狗", words);

    bool found = false;
    for (const auto& w : words) {
        if (w == "狗") { found = true; break; }
    }
    EXPECT_TRUE(found);
}

// 直接分词：单字作为多字词的子串也应被 CutForSearch 产出（如“熊猫”产出“猫”）
TEST(TokenizerSingleChar, DirectMaoInsideWordTokenized) {
    requireJiebaAvailable();
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr);

    std::vector<std::string> words;
    jieba->CutForSearch("熊猫是国宝动物", words);

    bool found = false;
    for (const auto& w : words) {
        if (w == "猫") { found = true; break; }
    }
    EXPECT_TRUE(found);
}

// 端到端：注册 jieba 分词器到 sqlite 连接应返回 SQLITE_OK
TEST(TokenizerSingleChar, RegisterJiebaTokenizerOk) {
    std::string dir = makeTempDir("docseek_single_register");
    std::string dbPath = dir + "/index.db";

    sqlite3* raw = nullptr;
    ASSERT_EQ(sqlite3_open(dbPath.c_str(), &raw), SQLITE_OK);
    ASSERT_NE(raw, nullptr);

    int rc = docseek::registerJiebaTokenizer(raw);
    EXPECT_EQ(rc, SQLITE_OK) << "jieba init error: " << docseek::jiebaInitError();

    sqlite3_close(raw);
}

// 单字“的”在标题中出现时能被召回
TEST(TokenizerSingleChar, DeInTitle) {
    std::string dir = makeTempDir("docseek_single_de_title");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/de_title.txt", "的的的", "无关内容", 10, 100);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("的", 10);

    EXPECT_GE(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].path, std::string("/de_title.txt"));
}

// 单字“的”在正文中出现时能被召回
TEST(TokenizerSingleChar, DeInBody) {
    std::string dir = makeTempDir("docseek_single_de_body");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/de_body.txt", "标题", "这是一段包含的字的正文", 10, 100);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("的", 10);

    EXPECT_GE(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].path, std::string("/de_body.txt"));
}

// 单字“猫”在标题中出现时能被召回
TEST(TokenizerSingleChar, MaoInTitle) {
    std::string dir = makeTempDir("docseek_single_mao_title");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/mao_title.txt", "猫", "正文里没有这个字", 10, 100);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("猫", 10);

    EXPECT_GE(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].path, std::string("/mao_title.txt"));
}

// 单字“猫”在正文中出现时能被召回
TEST(TokenizerSingleChar, MaoInBody) {
    std::string dir = makeTempDir("docseek_single_mao_body");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/mao_body.txt", "标题", "我家养了一只猫", 10, 100);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("猫", 10);

    EXPECT_GE(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].path, std::string("/mao_body.txt"));
}

// 单字“狗”在标题中出现时能被召回
TEST(TokenizerSingleChar, GouInTitle) {
    std::string dir = makeTempDir("docseek_single_gou_title");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/gou_title.txt", "狗", "正文里没有这个字", 10, 100);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("狗", 10);

    EXPECT_GE(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].path, std::string("/gou_title.txt"));
}

// 单字“狗”在正文中出现时能被召回
TEST(TokenizerSingleChar, GouInBody) {
    std::string dir = makeTempDir("docseek_single_gou_body");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/gou_body.txt", "标题", "院子里跑着一条狗", 10, 100);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("狗", 10);

    EXPECT_GE(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].path, std::string("/gou_body.txt"));
}

// 单字在标题与正文都出现时，两条不同文档都应命中
TEST(TokenizerSingleChar, SameCharInTitleAndBodyHitsBothDocs) {
    std::string dir = makeTempDir("docseek_single_both_docs");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/hit_title.txt", "猫", "无关内容", 10, 100);
    db.upsert("/hit_body.txt", "标题", "正文里有一只猫", 10, 100);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("猫", 10);

    EXPECT_GE(hits.size(), 2u);
    bool foundTitle = false;
    bool foundBody = false;
    for (const auto& h : hits) {
        if (h.path == std::string("/hit_title.txt")) foundTitle = true;
        if (h.path == std::string("/hit_body.txt")) foundBody = true;
    }
    EXPECT_TRUE(foundTitle);
    EXPECT_TRUE(foundBody);
}

// 单字在一个文档的标题和正文都出现时，仍只返回一条该文档
TEST(TokenizerSingleChar, SameDocTitleAndBodySingleHit) {
    std::string dir = makeTempDir("docseek_single_one_doc");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/one_doc.txt", "猫", "正文里也有一只猫", 10, 100);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("猫", 10);

    EXPECT_GE(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].path, std::string("/one_doc.txt"));
}

// 单字“的”在标题和正文都出现，仍只返回一条
TEST(TokenizerSingleChar, DeInBothPlacesSingleHit) {
    std::string dir = makeTempDir("docseek_single_de_one");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/de_one.txt", "的", "这里也有的字", 10, 100);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("的", 10);

    EXPECT_GE(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].path, std::string("/de_one.txt"));
}

// 单字查询在词中也有命中：包含“猫”作为词素的多字词应能匹配
TEST(TokenizerSingleChar, MaoInsideWordHits) {
    std::string dir = makeTempDir("docseek_single_mao_word");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/mao_word.txt", "标题", "熊猫是国宝动物", 10, 100);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("猫", 10);

    EXPECT_GE(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].path, std::string("/mao_word.txt"));
}

// 单字“狗”在词中命中：如“猎狗”
TEST(TokenizerSingleChar, GouInsideWordHits) {
    std::string dir = makeTempDir("docseek_single_gou_word");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/gou_word.txt", "标题", "猎狗跑得很快", 10, 100);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("狗", 10);

    EXPECT_GE(hits.size(), 1u);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].path, std::string("/gou_word.txt"));
}

// 单字查询不应召回完全无关的文档
TEST(TokenizerSingleChar, UnrelatedDocNotHit) {
    std::string dir = makeTempDir("docseek_single_unrelated");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/unrelated.txt", "电脑", "这是一台新电脑", 10, 100);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("猫", 10);

    bool foundUnrelated = false;
    for (const auto& h : hits) {
        if (h.path == std::string("/unrelated.txt")) foundUnrelated = true;
    }
    EXPECT_FALSE(foundUnrelated);
    EXPECT_TRUE(hits.empty());
}