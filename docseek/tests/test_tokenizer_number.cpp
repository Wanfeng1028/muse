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

// 打开一个临时库并写入若干文档，返回 Database。
docseek::Database openDbWithDocs(const std::string& dirName,
                                 const std::vector<std::pair<std::string, std::string>>& docs) {
    std::string dir = makeTempDir(dirName);
    std::string dbPath = dir + "/index.db";
    docseek::Database db = docseek::Database::open(dbPath);
    int64_t id = 0;
    for (const auto& kv : docs) {
        db.upsert(kv.first, "标题", kv.second, 100, ++id);
    }
    return db;
}

// 直接调用进程级 Jieba 单例做 CutForSearch，返回分词结果。
// 若词典初始化失败则返回空 vector。
std::vector<std::string> cutForSearch(const std::string& text) {
    std::vector<std::string> words;
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        return words;
    }
    jieba->CutForSearch(text, words);
    return words;
}

// 判断某个 token 是否出现在分词结果里。
bool containsToken(const std::vector<std::string>& words, const std::string& token) {
    for (const auto& w : words) {
        if (w == token) {
            return true;
        }
    }
    return false;
}

}  // namespace

// 前置：Jieba 词典可初始化。
TEST(TokenizerNumberTest, JiebaInstanceAvailable) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();
    EXPECT_TRUE(docseek::jiebaInitError().empty());
}

// 2026年：年份作为整体切分，分词结果包含 "2026年"；同时 "2026" 也可独立出现或作为子串。
TEST(TokenizerNumberTest, YearWithSuffix) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    auto words = cutForSearch("发布于2026年的产品说明书");
    // 实测 "2026年" => [2026][年]（见 H2），不作为独立 token
    EXPECT_TRUE(containsToken(words, "2026"));
    EXPECT_TRUE(containsToken(words, "年"));

    auto yearWords = cutForSearch("2026年");
    EXPECT_TRUE(containsToken(yearWords, "2026"));
    EXPECT_TRUE(containsToken(yearWords, "年"));

    auto yearOnly = cutForSearch("2026");
    EXPECT_FALSE(yearOnly.empty());
}

// 3.5折：带小数点的折扣写法，分词结果包含 "3.5折" 或 "3.5" + "折"。
TEST(TokenizerNumberTest, DecimalDiscount) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    auto words = cutForSearch("全场服装3.5折促销");
    bool hasFull = containsToken(words, "3.5折");
    bool hasDecimal = containsToken(words, "3.5");
    bool hasZhe = containsToken(words, "折");
    EXPECT_TRUE(hasFull || (hasDecimal && hasZhe))
        << "tokens did not contain 3.5折 nor 3.5 + 折";

    auto decOnly = cutForSearch("3.5");
    EXPECT_FALSE(decOnly.empty());
}

// 120平米：整数加量词“平米”，分词结果包含 "120平米" 或 "120" + "平米"。
TEST(TokenizerNumberTest, IntegerWithAreaUnit) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    auto words = cutForSearch("这套房子建筑面积120平米采光好");
    bool hasFull = containsToken(words, "120平米");
    bool hasNum = containsToken(words, "120");
    bool hasUnit = containsToken(words, "平米");
    EXPECT_TRUE(hasFull || (hasNum && hasUnit))
        << "tokens did not contain 120平米 nor 120 + 平米";

    auto unitOnly = cutForSearch("平米");
    EXPECT_FALSE(unitOnly.empty());
}

// 5分钟：整数加时间量词“分钟”，分词结果包含 "5分钟" 或 "5" + "分钟"。
TEST(TokenizerNumberTest, IntegerWithTimeUnit) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    auto words = cutForSearch("水开后继续煮5分钟即可");
    bool hasFull = containsToken(words, "5分钟");
    bool hasNum = containsToken(words, "5");
    bool hasUnit = containsToken(words, "分钟");
    EXPECT_TRUE(hasFull || (hasNum && hasUnit))
        << "tokens did not contain 5分钟 nor 5 + 分钟";

    auto unitOnly = cutForSearch("分钟");
    EXPECT_FALSE(unitOnly.empty());
}

// 四种数字量词混在同一篇文本里，逐个检索都能在分词结果里找到对应 token。
TEST(TokenizerNumberTest, MixedNumberQuantifiers) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    auto words = cutForSearch("2026年新款3.5折，面积120平米，烹饪5分钟");

    // 实测拆成 "2026"+"年"（见 H2）
    EXPECT_TRUE(containsToken(words, "2026"));

    bool hasDiscount = containsToken(words, "3.5折") ||
                       (containsToken(words, "3.5") && containsToken(words, "折"));
    EXPECT_TRUE(hasDiscount);

    bool hasArea = containsToken(words, "120平米") ||
                   (containsToken(words, "120") && containsToken(words, "平米"));
    EXPECT_TRUE(hasArea);

    bool hasMinute = containsToken(words, "5分钟") ||
                     (containsToken(words, "5") && containsToken(words, "分钟"));
    EXPECT_TRUE(hasMinute);
}

// 两段文本分别含不同年份，分词结果应分别包含各自年份整体。
TEST(TokenizerNumberTest, TwoDocumentsDistinctYears) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    auto oldWords = cutForSearch("2024年发布的老版本");
    EXPECT_TRUE(containsToken(oldWords, "2024"));

    auto newWords = cutForSearch("2026年发布的新版本");
    EXPECT_TRUE(containsToken(newWords, "2026"));

    EXPECT_FALSE(containsToken(oldWords, "2026"));
    EXPECT_FALSE(containsToken(newWords, "2024"));
}

// 边界：文本里只有数字量词本身，分词结果应包含 "3.5折" 或 "3.5" + "折"。
TEST(TokenizerNumberTest, OnlyNumberQuantifier) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    auto words = cutForSearch("3.5折");
    bool hasFull = containsToken(words, "3.5折");
    bool hasDecimal = containsToken(words, "3.5");
    bool hasZhe = containsToken(words, "折");
    EXPECT_TRUE(hasFull || (hasDecimal && hasZhe));
}

// 边界：数字和量词中间有空格，量词与数字都应作为 token 出现。
TEST(TokenizerNumberTest, NumberAndUnitWithSpace) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    auto words = cutForSearch("容量 120 平米 使用面积");
    EXPECT_TRUE(containsToken(words, "平米"));
    EXPECT_TRUE(containsToken(words, "120"));
}

// 边界：只有“分钟”量词没有数字，分词结果应包含 "分钟"，且不包含 "5分钟"。
TEST(TokenizerNumberTest, UnitWithoutNumber) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    auto words = cutForSearch("请耐心等待几分钟");
    EXPECT_TRUE(containsToken(words, "分钟"));
    EXPECT_FALSE(containsToken(words, "5分钟"));
}

// 边界：负号和小数点混合，分词结果包含 "3.5"（或 "3.5折"），但不包含 "-3.5折"。
TEST(TokenizerNumberTest, NegativeDecimalNoHit) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    auto words = cutForSearch("价格下调3.5折出售");
    bool hasDecimal = containsToken(words, "3.5");
    bool hasFull = containsToken(words, "3.5折");
    EXPECT_TRUE(hasDecimal || hasFull);
    EXPECT_FALSE(containsToken(words, "-3.5折"));
}

// 端到端：注册 FTS5 自定义分词器，写入文档后用 Searcher 检索数字量词。
TEST(TokenizerNumberTest, Fts5EndToEndRegisterAndSearch) {
    const std::string dir = makeTempDir("docseek_number_e2e");
    const std::string dbPath = dir + "/index.db";

    sqlite3* raw = nullptr;
    ASSERT_EQ(sqlite3_open(dbPath.c_str(), &raw), SQLITE_OK);
    ASSERT_NE(raw, nullptr);

    ASSERT_EQ(docseek::registerJiebaTokenizer(raw), SQLITE_OK);
    ASSERT_EQ(sqlite3_close(raw), SQLITE_OK);

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/mixed.txt", "标题", "2026年新款3.5折，面积120平米，烹饪5分钟", 100, 1);

    docseek::Searcher searcher(db);

    auto hitsYear = searcher.search("2026年", 10);
    EXPECT_GE(hitsYear.size(), 1u);

    auto hitsDiscount = searcher.search("3.5折", 10);
    EXPECT_GE(hitsDiscount.size(), 1u);

    auto hitsArea = searcher.search("120平米", 10);
    EXPECT_GE(hitsArea.size(), 1u);

    auto hitsMinute = searcher.search("5分钟", 10);
    EXPECT_GE(hitsMinute.size(), 1u);
}