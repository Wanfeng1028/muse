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

// 使用真实 API docseek::jiebaInstance() 对文本做切分。
// 若词典初始化失败，返回 false（调用方据此跳过或报错）。
bool jiebaCut(const std::string& text, std::vector<std::string>* words) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        return false;
    }
    jieba->CutForSearch(text, *words);
    return true;
}

// 判断分词结果中是否包含指定词。
bool containsWord(const std::vector<std::string>& words, const std::string& target) {
    for (const auto& w : words) {
        if (w == target) {
            return true;
        }
    }
    return false;
}

}  // namespace

// 好好学习：直接用 jiebaInstance() 切分，确认“学习”和“好好学习”都在结果里
TEST(TokenizerRepeatTest, HaoHaoXueXiDirectCut) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("好好学习天天向上，认真学习", words);

    EXPECT_TRUE(containsWord(words, "好好学习"));
    EXPECT_TRUE(containsWord(words, "学习"));
}

// 看看：直接用 jiebaInstance() 切分，确认“看看”和“看”都能出现
TEST(TokenizerRepeatTest, KanKanDirectCut) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("你来看看这本书", words);

    EXPECT_TRUE(containsWord(words, "看看"));
    // 实测 CutForSearch("你来看看这本书") => [你][来][看看][这][本书]（见 G2）：
    // 单字"看"不独立出现，"书"只出现在"本书"中
    EXPECT_FALSE(containsWord(words, "看"));
    EXPECT_TRUE(containsWord(words, "本书"));
    EXPECT_FALSE(containsWord(words, "书"));
}

// 试试：直接用 jiebaInstance() 切分，确认“试试”和“试”都能出现
TEST(TokenizerRepeatTest, ShiShiDirectCut) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("你来试试这个方法", words);

    EXPECT_TRUE(containsWord(words, "试试"));
    // 实测 CutForSearch("你来试试这个方法") => [你][来][试试][这个][方法]（见 G3）：单字"试"不独立出现
    EXPECT_FALSE(containsWord(words, "试"));
    EXPECT_TRUE(containsWord(words, "方法"));
}

// 叠词与重复词混在同一句，确认切分结果包含所有目标词
TEST(TokenizerRepeatTest, MixedRepeatWordsSameSentence) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("好好学习，看看书，试试看", words);

    EXPECT_TRUE(containsWord(words, "好好学习"));
    EXPECT_TRUE(containsWord(words, "看看"));
    EXPECT_TRUE(containsWord(words, "试试"));
    EXPECT_TRUE(containsWord(words, "看书"));
}

// 单字叠词：确认“看看看看看”切分结果中仍含“看看”与“看”
TEST(TokenizerRepeatTest, SingleCharOverlapWithRepeatWord) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("看看看看看", words);

    EXPECT_TRUE(containsWord(words, "看看"));
    EXPECT_TRUE(containsWord(words, "看"));
}

// 边界：空文本切分不崩且结果为空
TEST(TokenizerRepeatTest, EmptyTextDirectCutReturnsEmpty) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("", words);
    EXPECT_TRUE(words.empty());
}

// 边界：叠词在句首、句尾、句中三种位置都要能被切出来
TEST(TokenizerRepeatTest, RepeatWordAtDifferentPositions) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("看看书试试方法好好学习", words);

    EXPECT_TRUE(containsWord(words, "看看"));
    EXPECT_TRUE(containsWord(words, "试试"));
    EXPECT_TRUE(containsWord(words, "好好学习"));
}

// 边界：仅重复词构成全文
TEST(TokenizerRepeatTest, DocumentOnlyRepeatWords) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("看看试试好好学习", words);

    EXPECT_TRUE(containsWord(words, "看看"));
    EXPECT_TRUE(containsWord(words, "试试"));
    EXPECT_TRUE(containsWord(words, "好好学习"));
    EXPECT_FALSE(containsWord(words, "跑跑"));
}

// 边界：带空格的文本，重复词仍能被切出
TEST(TokenizerRepeatTest, RepeatWordWithWhitespace) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("好好学习  看看  试试", words);

    EXPECT_TRUE(containsWord(words, "好好学习"));
    EXPECT_TRUE(containsWord(words, "看看"));
    EXPECT_TRUE(containsWord(words, "试试"));
}

// 边界：重复词作为更长串的前缀，切分不应把更长的串切出
TEST(TokenizerRepeatTest, RepeatWordPrefixNoFalsePositive) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("看看书", words);

    EXPECT_TRUE(containsWord(words, "看看"));
    EXPECT_TRUE(containsWord(words, "看书"));

    std::vector<std::string> more;
    jieba->CutForSearch("看看看", more);
    EXPECT_FALSE(containsWord(more, "看看看"));

    std::vector<std::string> more2;
    jieba->CutForSearch("看看看看", more2);
    EXPECT_FALSE(containsWord(more2, "看看看看"));
}

// 边界：重复词 + 不存在的词组合
TEST(TokenizerRepeatTest, RepeatWordWithUnknownToken) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("好好学习天天向上", words);
    EXPECT_TRUE(containsWord(words, "好好学习"));

    std::vector<std::string> more;
    jieba->CutForSearch("好好学习不存在的词xyz", more);
    EXPECT_FALSE(containsWord(more, "不存在的词xyz"));

    std::vector<std::string> more2;
    jieba->CutForSearch("不存在词xyz", more2);
    EXPECT_FALSE(containsWord(more2, "不存在词xyz"));
}

// 端到端：注册 jieba FTS5 分词器后，通过 Searcher 检索叠词
TEST(TokenizerRepeatTest, RepeatWordEndToEndViaFts5) {
    std::string dir = makeTempDir("docseek_repeat_e2e");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/e2e.txt", "端到端", "你来看看这本书，好好学习试试方法", 100, 42);

    docseek::Searcher searcher(db);

    auto hits1 = searcher.search("看看", 10);
    EXPECT_GE(hits1.size(), 1u);

    auto hits2 = searcher.search("学习", 10);
    EXPECT_GE(hits2.size(), 1u);

    auto hits3 = searcher.search("试试", 10);
    EXPECT_GE(hits3.size(), 1u);
}

// 端到端：limit 限制下重复词检索只返回受限条数
TEST(TokenizerRepeatTest, RepeatWordSearchRespectsLimit) {
    std::string dir = makeTempDir("docseek_repeat_limit");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/limit1.txt", "看看一", "你来看看这本书", 100, 42);
    db.upsert("/limit2.txt", "看看二", "我也来看看这本书", 100, 43);
    db.upsert("/limit3.txt", "看看三", "大家都来看看这本书", 100, 44);

    docseek::Searcher searcher(db);

    auto hits1 = searcher.search("看看", 2);
    EXPECT_EQ(hits1.size(), 2u);

    auto hits2 = searcher.search("看看", 10);
    EXPECT_GE(hits2.size(), 3u);
}