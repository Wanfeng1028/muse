// 锁定 2026-10-18 新增 fillerWords（知道/什么/什么时候/怎么办/的话/比较）的问句噪音过滤行为。
// 涉及 jieba 切分不确定的用例，只断言"不含噪音词"，避免把分词结果写死。
#include <gtest/gtest.h>

#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"
#include "docseek/query_parser.h"

namespace docseek {
namespace {

// 取进程 pid，用于隔离并行测试产生的临时目录。
static long currentPid() {
#ifndef _WIN32
    return static_cast<long>(::getpid());
#else
    return 0L;
#endif
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

// 与 tests/test_query_parser.cpp 一致的包含断言风格。
template <typename T>
bool contains(const std::vector<T>& vec, const T& value) {
    for (const auto& item : vec) {
        if (item == value) {
            return true;
        }
    }
    return false;
}

}  // namespace

// (a) "我想知道退款流程"：应剥离 "想知道"，保留 退款/流程 语义。
TEST(FillerWordsV015, StripsXiangZhiDaoKeepsDomainWords) {
    requireJiebaReady();
    ParsedQuery parsed = parseNaturalQuery("我想知道退款流程");
    EXPECT_TRUE(contains(parsed.keywords, std::string("退款")))
        << "退款 不应被过滤";
    EXPECT_TRUE(contains(parsed.keywords, std::string("流程")))
        << "流程 不应被过滤";
    EXPECT_FALSE(contains(parsed.keywords, std::string("知道")))
        << "知道 属于 v0.15 新增噪音词，应被剥离";
    EXPECT_FALSE(contains(parsed.keywords, std::string("想")))
        << "想 属于单字停用词，应被剥离";
}

// (b) 长问句里 "什么时候" 被剥离，正文词保留。
TEST(FillerWordsV015, StripsShenMeShiHouInLongQuestion) {
    requireJiebaReady();
    ParsedQuery parsed =
        parseNaturalQuery("自由泳换气的时候头应该什么时候转过去");
    EXPECT_FALSE(contains(parsed.keywords, std::string("什么时候")))
        << "什么时候 应被剥离";
    EXPECT_TRUE(contains(parsed.keywords, std::string("自由泳")))
        << "自由泳 不应被过滤";
}

// (c) "怎么办" 属于 v0.15 新增噪音词。
TEST(FillerWordsV015, StripsZenMeBan) {
    requireJiebaReady();
    ParsedQuery parsed = parseNaturalQuery("怕水怎么办");
    EXPECT_FALSE(contains(parsed.keywords, std::string("怎么办")))
        << "怎么办 应被剥离";
    EXPECT_TRUE(contains(parsed.keywords, std::string("怕水")))
        << "怕水 不应被过滤";
}

// (d) "的话" 被剥离，剩下的处理语义保留。
TEST(FillerWordsV015, StripsDeHua) {
    requireJiebaReady();
    ParsedQuery parsed = parseNaturalQuery("长期不弹琴的话怎么处理");
    EXPECT_FALSE(contains(parsed.keywords, std::string("的话")))
        << "的话 应被剥离";
    EXPECT_TRUE(contains(parsed.keywords, std::string("弹琴")))
        << "弹琴 不应被过滤";
}

// (e) "比较合适" 整串优先于 "比较"，不应残留 比较/合适。
TEST(FillerWordsV015, StripsBiJiaoAndHeShiAsWholePhrase) {
    requireJiebaReady();
    ParsedQuery parsed = parseNaturalQuery("哪种比较合适");
    EXPECT_FALSE(contains(parsed.keywords, std::string("比较")))
        << "比较 应被剥离";
    EXPECT_FALSE(contains(parsed.keywords, std::string("合适")))
        << "比较合适 整串优先，合适 也应被剥离";
}

// (f) "不" 永不入表：否定语义保护，parseNaturalQuery 结果非空。
TEST(FillerWordsV015, PreservesNegationBu) {
    requireJiebaReady();
    ParsedQuery parsed = parseNaturalQuery("不建议熬夜");
    EXPECT_FALSE(parsed.keywords.empty())
        << "不 属于否定语义，不应导致整句被清空";
    // 保守：不做硬断言（jieba 可能把 不 并入 不建议 或单独成词）。
}

// (g) "知道" 单独出现被剥离，"知识" 保留。
TEST(FillerWordsV015, StripsZhiDaoButKeepsZhiShi) {
    requireJiebaReady();
    ParsedQuery parsed = parseNaturalQuery("我想知道知识产权");
    EXPECT_FALSE(contains(parsed.keywords, std::string("知道")))
        << "知道 应被剥离";
    // jieba 可能切出 知识产权 或 知识，只断言其一存在。
    const bool hasFull = contains(parsed.keywords, std::string("知识产权"));
    const bool hasShort = contains(parsed.keywords, std::string("知识"));
    EXPECT_TRUE(hasFull || hasShort)
        << "知识/知识产权 至少一个应保留";
}

// (h) 短问句回归：v0.12 已有行为不应被 v0.15 噪音表回归破坏。
TEST(FillerWordsV015, RegressionShortQuestionKeepsDomainWords) {
    requireJiebaReady();
    ParsedQuery parsed = parseNaturalQuery("退款流程写在哪一段");
    EXPECT_TRUE(contains(parsed.keywords, std::string("退款")))
        << "退款 不应被过滤";
    EXPECT_TRUE(contains(parsed.keywords, std::string("流程")))
        << "流程 不应被过滤";
}

// (i) "什么" 单独出现时被剥离。
TEST(FillerWordsV015, StripsShenMe) {
    requireJiebaReady();
    ParsedQuery parsed = parseNaturalQuery("什么是缓存穿透");
    EXPECT_FALSE(contains(parsed.keywords, std::string("什么")))
        << "什么 应被剥离";
    // 不硬断言切分结果，只要求语义主体未被整句清空。
    EXPECT_FALSE(parsed.keywords.empty())
        << "缓存穿透 类问题不应被清空";
}

// (j) "比较" 单独出现（无 "合适" 后缀）也被剥离。
TEST(FillerWordsV015, StripsBiJiaoAlone) {
    requireJiebaReady();
    ParsedQuery parsed = parseNaturalQuery("哪个比较省电");
    EXPECT_FALSE(contains(parsed.keywords, std::string("比较")))
        << "比较 应被剥离";
    EXPECT_TRUE(contains(parsed.keywords, std::string("省电")))
        << "省电 不应被过滤";
}

}  // namespace docseek
