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

// 打开一个用于本组用例的临时数据库，返回路径
docseek::Database openTempDb(const std::string& name) {
    std::string dir = makeTempDir(name);
    return docseek::Database::open(dir + "/index.db");
}

// 判断一个混排 token 是否会被 jieba 的 CutForSearch 切成包含该 token 的片段
bool jiebaProducesToken(const std::string& text, const std::string& token) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        return false;
    }
    std::vector<std::string> words;
    jieba->CutForSearch(text, words);
    for (const auto& w : words) {
        if (w == token) {
            return true;
        }
    }
    return false;
}

}  // namespace

// 用例 1：纯英文数字组合 iPhone15 作为一个整体可被检索到
TEST(TokenizerMixedTest, IPhone15WholeTokenSearchable) {
    docseek::Database db = openTempDb("docseek_mixed_iphone15");
    db.upsert("/a.txt", "标题", "我买了 iPhone15 很开心", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("iPhone15", 10);
    EXPECT_GE(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, "/a.txt");
}

// 用例 2：汉字紧贴字母数字时，英文数字段仍可被检索
TEST(TokenizerMixedTest, ChineseAdjacentToLatin) {
    docseek::Database db = openTempDb("docseek_mixed_adjacent");
    db.upsert("/b.txt", "标题", "测试5G网络速度", 100, 42);

    docseek::Searcher searcher(db);

    auto hits5g = searcher.search("5G", 10);
    EXPECT_GE(hits5g.size(), 1u);
    EXPECT_EQ(hits5g[0].path, "/b.txt");

    auto hitsChinese = searcher.search("网络", 10);
    EXPECT_GE(hitsChinese.size(), 1u);
}

// 用例 3：全大写缩写 OKR 作为独立 token 可被检索
TEST(TokenizerMixedTest, UppercaseAbbreviationOKR) {
    docseek::Database db = openTempDb("docseek_mixed_okr");
    db.upsert("/c.txt", "标题", "本季度 OKR 完成情况", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("OKR", 10);
    EXPECT_GE(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, "/c.txt");
}

// 用例 4：全大写缩写 KPI 作为独立 token 可被检索
TEST(TokenizerMixedTest, UppercaseAbbreviationKPI) {
    docseek::Database db = openTempDb("docseek_mixed_kpi");
    db.upsert("/d.txt", "标题", "团队 KPI 达成率很高", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("KPI", 10);
    EXPECT_GE(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, "/d.txt");
}

// 用例 5：多个混排 token 在同一篇文档里都能被分别检索到
TEST(TokenizerMixedTest, MultipleMixedTokensInOneDoc) {
    docseek::Database db = openTempDb("docseek_mixed_multi");
    db.upsert("/e.txt", "标题",
              "iPhone15 支持 5G，团队 OKR 与 KPI 都要看", 100, 42);

    docseek::Searcher searcher(db);

    auto hitsPhone = searcher.search("iPhone15", 10);
    EXPECT_GE(hitsPhone.size(), 1u);

    auto hits5g = searcher.search("5G", 10);
    EXPECT_GE(hits5g.size(), 1u);

    auto hitsOkr = searcher.search("OKR", 10);
    EXPECT_GE(hitsOkr.size(), 1u);

    auto hitsKpi = searcher.search("KPI", 10);
    EXPECT_GE(hitsKpi.size(), 1u);
}

// 用例 6：字母数字与汉字之间没有空格时，汉字部分仍可检索
TEST(TokenizerMixedTest, NoSpaceChineseAfterDigits) {
    docseek::Database db = openTempDb("docseek_mixed_nospace");
    db.upsert("/f.txt", "标题", "共100台服务器在线", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("服务器", 10);
    EXPECT_GE(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, "/f.txt");
}

// 用例 7：字母数字串大小写不同视为不同 token，原样大写可命中
TEST(TokenizerMixedTest, CaseSensitiveLatinToken) {
    docseek::Database db = openTempDb("docseek_mixed_case");
    db.upsert("/g.txt", "标题", "接口叫 API 网关", 100, 42);

    docseek::Searcher searcher(db);

    auto hitsUpper = searcher.search("API", 10);
    EXPECT_GE(hitsUpper.size(), 1u);
    EXPECT_EQ(hitsUpper[0].path, "/g.txt");

    auto hitsChinese = searcher.search("网关", 10);
    EXPECT_GE(hitsChinese.size(), 1u);
}

// 用例 8：不含字母数字混排的词应检索不到
TEST(TokenizerMixedTest, AbsentMixedTokenReturnsEmpty) {
    docseek::Database db = openTempDb("docseek_mixed_absent");
    db.upsert("/h.txt", "标题", "这是一篇普通的中文文档", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("iPhone99", 10);
    EXPECT_TRUE(hits.empty());

    auto hits2 = searcher.search("6G", 10);
    EXPECT_TRUE(hits2.empty());
}

// 用例 9：字母数字与汉字混排的短标题仍能被检索
TEST(TokenizerMixedTest, ShortMixedTitleSearchable) {
    docseek::Database db = openTempDb("docseek_mixed_short");
    db.upsert("/i.txt", "标题", "OKR与KPI", 100, 42);

    docseek::Searcher searcher(db);

    auto hitsOkr = searcher.search("OKR", 10);
    EXPECT_GE(hitsOkr.size(), 1u);
    EXPECT_EQ(hitsOkr[0].path, "/i.txt");

    auto hitsKpi = searcher.search("KPI", 10);
    EXPECT_GE(hitsKpi.size(), 1u);
}

// 用例 10：数字加单位混排（5G、4K）与纯汉字混合时互不干扰
TEST(TokenizerMixedTest, DigitUnitTokensDoNotPolluteChinese) {
    docseek::Database db = openTempDb("docseek_mixed_digitunit");
    db.upsert("/j.txt", "标题", "5G 网络和 4K 视频都要测", 100, 42);

    docseek::Searcher searcher(db);

    auto hits5g = searcher.search("5G", 10);
    EXPECT_GE(hits5g.size(), 1u);

    auto hits4k = searcher.search("4K", 10);
    EXPECT_GE(hits4k.size(), 1u);

    auto hitsVideo = searcher.search("视频", 10);
    EXPECT_GE(hitsVideo.size(), 1u);
}

// 用例 11：同一混排 token 命中多篇文档时结果集应包含全部
TEST(TokenizerMixedTest, MixedTokenMatchesMultipleDocs) {
    docseek::Database db = openTempDb("docseek_mixed_multi_doc");
    db.upsert("/k1.txt", "标题", "第一篇讲 iPhone15 的文章", 100, 42);
    db.upsert("/k2.txt", "标题", "第二篇也提到 iPhone15", 100, 43);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("iPhone15", 10);
    EXPECT_GE(hits.size(), 2u);
    bool foundK1 = false;
    bool foundK2 = false;
    for (const auto& h : hits) {
        if (h.path == "/k1.txt") foundK1 = true;
        if (h.path == "/k2.txt") foundK2 = true;
    }
    EXPECT_TRUE(foundK1);
    EXPECT_TRUE(foundK2);
}

// 用例 12：混排 token 前后带标点时仍可被检索
TEST(TokenizerMixedTest, MixedTokenWithPunctuation) {
    docseek::Database db = openTempDb("docseek_mixed_punct");
    db.upsert("/l.txt", "标题", "他说：（iPhone15）很贵。", 100, 42);

    docseek::Searcher searcher(db);

    auto hits = searcher.search("iPhone15", 10);
    EXPECT_GE(hits.size(), 1u);
    EXPECT_EQ(hits[0].path, "/l.txt");
}

// 用例 13：直接验证 jiebaInstance 对混排文本的切分包含英文数字 token
TEST(TokenizerMixedTest, JiebaInstanceCutsMixedTokens) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    EXPECT_TRUE(jiebaProducesToken("我买了 iPhone15 很开心", "iPhone15"));
    // 实测 "测试5G网络速度" => [测试][5][G][网络][速度]（见 H1）："5G" 拆成 "5"+"G"
    EXPECT_FALSE(jiebaProducesToken("测试5G网络速度", "5G"));
    EXPECT_TRUE(jiebaProducesToken("测试5G网络速度", "5"));
    EXPECT_TRUE(jiebaProducesToken("测试5G网络速度", "G"));
    EXPECT_TRUE(jiebaProducesToken("本季度 OKR 完成情况", "OKR"));
    EXPECT_TRUE(jiebaProducesToken("团队 KPI 达成率很高", "KPI"));
}

// 用例 14：直接验证 CutForSearch 对纯汉字仍产出中文词
TEST(TokenizerMixedTest, JiebaInstanceCutsChinese) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();

    std::vector<std::string> words;
    jieba->CutForSearch("共100台服务器在线", words);
    bool found = false;
    for (const auto& w : words) {
        if (w == "服务器") {
            found = true;
            break;
        }
    }
    EXPECT_TRUE(found);
}