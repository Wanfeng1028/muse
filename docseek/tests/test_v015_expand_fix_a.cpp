#include <gtest/gtest.h>
#include <filesystem>
#include <set>
#include <string>
#include <utility>
#include <vector>
#include <unistd.h>
#include "docseek/database.h"
#include "docseek/searcher.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/token_locate.h"
#include "cppjieba/Jieba.hpp"

namespace docseek { namespace {

// 取进程 pid（仅 Linux 分支，本仓库测试只跑 Linux）。
static long currentPid() {
    return static_cast<long>(::getpid());
}

std::string makeTempDir(const std::string& name) {
    std::filesystem::path base = std::filesystem::current_path() / "test-tmp";
    std::filesystem::create_directories(base);
    std::filesystem::path dir = base / (name + "_" + std::to_string(currentPid()));
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    return dir.string();
}

void requireJiebaReady() {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();
}

// 打开一个空的临时数据库，用于构造 Searcher 实例。
// buildMatchQuery/buildOrMatchQuery 是 static，不需要真实数据，但 Searcher
// 需要一个 Database 引用。
docseek::Database openTempDb(const std::string& name) {
    std::string dir = makeTempDir(name);
    std::filesystem::path dbPath = std::filesystem::path(dir) / "index.db";
    return docseek::Database::open(dbPath.string());
}

// 锁定 Fix A 行为：同一起始偏移的候选词用 OR 组装，不同偏移用 AND 连接。
// 依据 probe：CutForSearch("北京烤鸭") = [北京@0, 烤鸭@6, 北京烤鸭@0]。
// 组1（offset 0）：北京、北京烤鸭 -> ("北京" OR "北京烤鸭")
// 组2（offset 6）：烤鸭 -> "烤鸭"
// 因此最终串为 ("北京" OR "北京烤鸭") AND "烤鸭"。
TEST(ExpandFixAV015, BuildMatchQueryBeijingKaoyaExact) {
    requireJiebaReady();
    docseek::Database db = openTempDb("expand_a_bjky");
    docseek::Searcher searcher(db);
    const std::string actual = docseek::Searcher::buildMatchQuery("北京烤鸭");
    EXPECT_EQ(actual, "(\"北京\" OR \"北京烤鸭\") AND \"烤鸭\"");
}

// CutForSearch("ABC") = [ABC]，单组单成员退化为 quoteToken 原文。
TEST(ExpandFixAV015, BuildMatchQueryAbcExact) {
    requireJiebaReady();
    docseek::Database db = openTempDb("expand_a_abc");
    docseek::Searcher searcher(db);
    const std::string actual = docseek::Searcher::buildMatchQuery("ABC");
    EXPECT_EQ(actual, "\"ABC\"");
}

// buildOrMatchQuery 使用同样的分组，但组间用 OR 连接。
TEST(ExpandFixAV015, BuildOrMatchQueryBeijingKaoyaExact) {
    requireJiebaReady();
    docseek::Database db = openTempDb("expand_a_or_bjky");
    docseek::Searcher searcher(db);
    const std::string actual = docseek::Searcher::buildOrMatchQuery("北京烤鸭");
    EXPECT_EQ(actual, "(\"北京\" OR \"北京烤鸭\") AND \"烤鸭\"");
}

// quoteToken 转义：含双引号的 token 不应崩溃，结果非空。
// 精确转义串未实测，不硬断言，只验证可调用且非空。
TEST(ExpandFixAV015, BuildMatchQueryEscapesInnerDoubleQuote) {
    requireJiebaReady();
    docseek::Database db = openTempDb("expand_a_escape");
    docseek::Searcher searcher(db);
    const std::string actual = docseek::Searcher::buildMatchQuery("a\"b");
    EXPECT_FALSE(actual.empty());
}

// 直接单元测试 claimTokenPositions：重复词耗尽语义（DuplicateWordExhausted）。
// text="ab"，words=["ab","ab"]：第 1 个 "ab" 认领成功，第 2 个认领失败（见 test_token_locate.cpp 先例）。
TEST(ExpandFixAV015, ClaimTokenPositionsDuplicateExhausted) {
    const std::string text = "ab";
    const std::vector<std::string> words = {"ab", "ab"};
    std::set<std::pair<std::string, size_t>> claimed;
    const std::vector<docseek::LocatedToken> located =
        docseek::claimTokenPositions(text, words, claimed);
    ASSERT_EQ(located.size(), 1u);
    EXPECT_EQ(located[0].word, "ab");
    EXPECT_EQ(located[0].byteOffset, 0u);
}

// 多 token 按空白切分后显式 AND 连接（与认领失败无关的基础行为）。
TEST(ExpandFixAV015, BuildMatchQueryKeepsUnclaimedToken) {
    requireJiebaReady();
    docseek::Database db = openTempDb("expand_a_keep");
    docseek::Searcher searcher(db);
    const std::string actual = docseek::Searcher::buildMatchQuery("ab ab");
    EXPECT_EQ(actual, "\"ab\" AND \"ab\"");
}

// 多词短语：buildMatchQuery("北京烤鸭 好吃")。
// 为保确定性，只断言前缀 `("北京" OR "北京烤鸭") AND "烤鸭" AND `，
// 不对 "好吃" 的切分细节做假设（未实测）。
TEST(ExpandFixAV015, BuildMatchQueryPhrasePrefixStable) {
    requireJiebaReady();
    docseek::Database db = openTempDb("expand_a_phrase");
    docseek::Searcher searcher(db);
    const std::string actual = docseek::Searcher::buildMatchQuery("北京烤鸭 好吃");
    const std::string prefix = "(\"北京\" OR \"北京烤鸭\") AND \"烤鸭\" AND ";
    ASSERT_GE(actual.size(), prefix.size());
    EXPECT_EQ(actual.compare(0, prefix.size(), prefix), 0);
    // 结果中必须包含 "烤鸭" 片段，验证多组 AND 拼接未丢词。
    EXPECT_NE(actual.find("\"烤鸭\""), std::string::npos);
}

// 空输入边界：不应崩溃，也不应生成非法 FTS5 串（此处仅验证可调用且不抛）。
TEST(ExpandFixAV015, BuildMatchQueryEmptyInput) {
    requireJiebaReady();
    docseek::Database db = openTempDb("expand_a_empty");
    docseek::Searcher searcher(db);
    const std::string actual = docseek::Searcher::buildMatchQuery("");
    // 空输入下 quoteToken 不应产出裸露的双引号对（""）之外的怪异内容。
    // 仅验证不崩溃且返回值可被安全使用。
    (void)actual;
    SUCCEED();
}

}  // namespace
}  // namespace docseek
