#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"

#include <sqlite3.h>

#include <cstdint>
#include <filesystem>
#include <set>
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

// 断言 Jieba 单例已成功初始化（否则后续分词测试无意义）
void requireJiebaReady() {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();
}

// 用真实 API 对文本做分词：docseek::jiebaInstance()->CutForSearch(text, words)
std::vector<std::string> cutForSearch(const std::string& text) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    std::vector<std::string> words;
    if (jieba == nullptr) {
        return words;
    }
    jieba->CutForSearch(text, words);
    return words;
}

// 在给定文本的词序列中查找连续子序列 phraseWords 是否整体出现
bool containsConsecutive(const std::vector<std::string>& words,
                         const std::vector<std::string>& phraseWords) {
    if (phraseWords.empty() || phraseWords.size() > words.size()) {
        return false;
    }
    for (std::size_t i = 0; i + phraseWords.size() <= words.size(); ++i) {
        bool match = true;
        for (std::size_t j = 0; j < phraseWords.size(); ++j) {
            if (words[i + j] != phraseWords[j]) {
                match = false;
                break;
            }
        }
        if (match) {
            return true;
        }
    }
    return false;
}

}  // namespace

// 短语 "人工智能" 作为整体短语查询，应命中包含该连续短语的文档
TEST(TokenizerPhrase, PhraseArtificialIntelligenceHits) {
    requireJiebaReady();

    std::string dir = makeTempDir("docseek_phrase_ai");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/ai.txt", "人工智能", "人工智能正在改变世界", 100, 1);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("\"人工智能\"", 10);
    EXPECT_GE(hits.size(), 1u);
    if (!hits.empty()) {
        EXPECT_EQ(hits[0].path, "/ai.txt");
    }
}

// 短语 "全文检索" 作为整体短语查询，应命中包含该连续短语的文档
TEST(TokenizerPhrase, PhraseFullTextSearchHits) {
    requireJiebaReady();

    std::string dir = makeTempDir("docseek_phrase_fts");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/fts.txt", "全文检索", "全文检索系统的核心是倒排索引", 100, 2);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("\"全文检索\"", 10);
    EXPECT_GE(hits.size(), 1u);
    if (!hits.empty()) {
        EXPECT_EQ(hits[0].path, "/fts.txt");
    }
}

// 短语拆开出现（不连续）时，短语查询不应命中
TEST(TokenizerPhrase, PhraseNotAdjacentDoesNotHit) {
    requireJiebaReady();

    std::string dir = makeTempDir("docseek_phrase_nonadj");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/split.txt", "拆分", "人工的智能 与 智能的人工", 100, 3);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("\"人工智能\"", 10);
    EXPECT_TRUE(hits.empty());
}

// 短语查询大小写与中文无关，但应保证不同文档命中彼此隔离
TEST(TokenizerPhrase, PhraseHitsOnlyMatchingDocument) {
    requireJiebaReady();

    std::string dir = makeTempDir("docseek_phrase_isolate");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/yes.txt", "命中", "我们研究人工智能算法", 100, 4);
    db.upsert("/no.txt", "不命中", "人工操作与智能设备无关", 100, 5);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("\"人工智能\"", 10);
    ASSERT_GE(hits.size(), 1u);
    EXPECT_EQ(hits.size(), 1u);
    if (!hits.empty()) {
        EXPECT_EQ(hits[0].path, "/yes.txt");
    }
}

// 短语查询结果应支持多个文档同时命中
TEST(TokenizerPhrase, PhraseHitsMultipleDocuments) {
    requireJiebaReady();

    std::string dir = makeTempDir("docseek_phrase_multi");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/a.txt", "AI一", "人工智能是热门方向", 100, 6);
    db.upsert("/b.txt", "AI二", "人工智能赋能产业升级", 100, 7);
    db.upsert("/c.txt", "无关", "全文检索与分词", 100, 8);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("\"人工智能\"", 10);
    EXPECT_EQ(hits.size(), 2u);
    std::set<std::string> paths;
    for (const auto& h : hits) {
        paths.insert(h.path);
    }
    EXPECT_TRUE(paths.count("/a.txt") == 1);
    EXPECT_TRUE(paths.count("/b.txt") == 1);
    EXPECT_TRUE(paths.count("/c.txt") == 0);
}

// 空短语查询应返回空结果，不应抛异常
TEST(TokenizerPhrase, EmptyPhraseQueryReturnsEmpty) {
    requireJiebaReady();

    std::string dir = makeTempDir("docseek_phrase_empty");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/doc.txt", "标题", "全文检索测试", 100, 9);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("\"\"", 10);
    EXPECT_TRUE(hits.empty());
}

// 短语查询命中数量受 limit 参数约束
TEST(TokenizerPhrase, PhraseRespectsLimit) {
    requireJiebaReady();

    std::string dir = makeTempDir("docseek_phrase_limit");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/1.txt", "一", "全文检索入门", 100, 10);
    db.upsert("/2.txt", "二", "全文检索进阶", 100, 11);
    db.upsert("/3.txt", "三", "全文检索实战", 100, 12);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("\"全文检索\"", 2);
    EXPECT_EQ(hits.size(), 2u);
    EXPECT_LE(hits.size(), 2u);
}

// 短语查询应能命中标题字段
TEST(TokenizerPhrase, PhraseHitsTitleField) {
    requireJiebaReady();

    std::string dir = makeTempDir("docseek_phrase_title");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/t.txt", "人工智能导论", "这是一本教材", 100, 13);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("\"人工智能\"", 10);
    EXPECT_GE(hits.size(), 1u);
    if (!hits.empty()) {
        EXPECT_EQ(hits[0].path, "/t.txt");
    }
}

// 短语查询应能命中正文字段
TEST(TokenizerPhrase, PhraseHitsBodyField) {
    requireJiebaReady();

    std::string dir = makeTempDir("docseek_phrase_body");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/b.txt", "封面", "本文介绍全文检索的基本原理", 100, 14);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("\"全文检索\"", 10);
    EXPECT_GE(hits.size(), 1u);
    if (!hits.empty()) {
        EXPECT_EQ(hits[0].path, "/b.txt");
    }
}

// 短语查询不含词（整段不含该短语）时返回空
TEST(TokenizerPhrase, PhraseAbsentReturnsEmpty) {
    requireJiebaReady();

    std::string dir = makeTempDir("docseek_phrase_absent");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/x.txt", "无关", "今天天气不错适合散步", 100, 15);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("\"人工智能\"", 10);
    EXPECT_TRUE(hits.empty());
}

// 短语查询与单词查询结果一致（单文档包含该短语时）
TEST(TokenizerPhrase, PhraseAndWordQueryAgree) {
    requireJiebaReady();

    std::string dir = makeTempDir("docseek_phrase_agree");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/m.txt", "混合", "人工智能与全文检索结合", 100, 16);

    docseek::Searcher searcher(db);

    auto phraseHits = searcher.search("\"人工智能\"", 10);
    auto wordHits = searcher.search("人工智能", 10);
    EXPECT_GE(phraseHits.size(), 1u);
    EXPECT_GE(wordHits.size(), 1u);
    EXPECT_EQ(phraseHits.size(), wordHits.size());
}

// 直接分词验证：使用 docseek::jiebaInstance()->CutForSearch 得到词序列，
// 确认 "人工智能" 作为一个整体短语出现在分词结果中（连续子序列）。
TEST(TokenizerPhrase, DirectCutForSearchContainsPhrase) {
    requireJiebaReady();

    auto words = cutForSearch("人工智能正在改变世界");
    EXPECT_FALSE(words.empty());

    auto phraseWords = cutForSearch("人工智能");
    EXPECT_FALSE(phraseWords.empty());

    EXPECT_TRUE(containsConsecutive(words, phraseWords));
}

// 直接分词验证：非连续出现时，短语作为整体不应出现在词序列中。
TEST(TokenizerPhrase, DirectCutForSearchPhraseNotAdjacent) {
    requireJiebaReady();

    auto words = cutForSearch("人工的智能 与 智能的人工");
    auto phraseWords = cutForSearch("人工智能");
    EXPECT_FALSE(phraseWords.empty());

    EXPECT_FALSE(containsConsecutive(words, phraseWords));
}

// 端到端注册验证：registerJiebaTokenizer 在 sqlite3 连接上注册 "jieba" 分词器应返回 SQLITE_OK。
TEST(TokenizerPhrase, RegisterJiebaTokenizerSucceeds) {
    requireJiebaReady();

    sqlite3* raw = nullptr;
    ASSERT_EQ(sqlite3_open(":memory:", &raw), SQLITE_OK);
    ASSERT_NE(raw, nullptr);

    int rc = docseek::registerJiebaTokenizer(raw);
    EXPECT_EQ(rc, SQLITE_OK);

    sqlite3_close(raw);
}
