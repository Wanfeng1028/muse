// 生产级测试：停用词过滤边界（GAP-STOPWORD-001 落地后的深测）
// 说明：本文件仅覆盖停用词过滤的边界行为，不涉及 score 断言。
// 依赖：docseek 的 search / searchQuestion 接口（签名以源码原文为准）。

#include <gtest/gtest.h>

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

// 说明：以下头文件路径与符号名必须与源码逐字一致；
// 若仓库中实际包含路径不同，请按源码原文调整 include（不得编造签名）。
#include "docseek/docseek.h"

namespace {

namespace fs = std::filesystem;

// 每个 TEST 独立创建临时目录，避免相互污染。
class TempDir {
public:
    TempDir() {
        // 使用系统临时目录 + 唯一后缀，保证独立。
        fs::path base = fs::temp_directory_path();
        static std::atomic<unsigned> counter{0};
        unsigned id = counter.fetch_add(1, std::memory_order_relaxed);
        char buf[64];
        std::snprintf(buf, sizeof(buf), "docseek_stopword_v015_%u_%lld",
                      id, static_cast<long long>(::getpid()));
        dir_ = base / buf;
        std::error_code ec;
        fs::create_directories(dir_, ec);
    }

    ~TempDir() {
        std::error_code ec;
        fs::remove_all(dir_, ec);
    }

    const fs::path& path() const { return dir_; }

    // 写入一个文档，返回其绝对路径。
    fs::path writeDoc(const std::string& filename, const std::string& content) const {
        fs::path p = dir_ / filename;
        std::ofstream ofs(p, std::ios::binary | std::ios::trunc);
        ofs << content;
        ofs.close();
        return p;
    }

private:
    fs::path dir_;
};

// 将若干文档路径加入索引（具体 API 以源码原文为准）。
// 这里通过 docseek::Index 完成建索；若源码提供的是 free function，请按原文替换。
void buildIndex(docseek::Index& index, const std::vector<fs::path>& docs) {
    for (const auto& d : docs) {
        index.addFile(d.string());
    }
    index.commit();
}

// 1) 纯停用词 "的" -> 0 hits
TEST(StopwordEdgeV015, PureStopword_De_ReturnsZeroHits) {
    TempDir tmp;
    tmp.writeDoc("a.txt", "苹果 香蕉 橙子");

    docseek::Index index;
    buildIndex(index, {tmp.path() / "a.txt"});

    auto results = index.search("的");
    EXPECT_EQ(results.size(), 0u);
}

// 2) 纯停用词 "了" -> 0 hits
TEST(StopwordEdgeV015, PureStopword_Le_ReturnsZeroHits) {
    TempDir tmp;
    tmp.writeDoc("a.txt", "苹果 香蕉 橙子");

    docseek::Index index;
    buildIndex(index, {tmp.path() / "a.txt"});

    auto results = index.search("了");
    EXPECT_EQ(results.size(), 0u);
}

// 3) 纯停用词 "在" -> 0 hits
TEST(StopwordEdgeV015, PureStopword_Zai_ReturnsZeroHits) {
    TempDir tmp;
    tmp.writeDoc("a.txt", "苹果 香蕉 橙子");

    docseek::Index index;
    buildIndex(index, {tmp.path() / "a.txt"});

    auto results = index.search("在");
    EXPECT_EQ(results.size(), 0u);
}

// 4) 纯停用词 "是" -> 0 hits
TEST(StopwordEdgeV015, PureStopword_Shi_ReturnsZeroHits) {
    TempDir tmp;
    tmp.writeDoc("a.txt", "苹果 香蕉 橙子");

    docseek::Index index;
    buildIndex(index, {tmp.path() / "a.txt"});

    auto results = index.search("是");
    EXPECT_EQ(results.size(), 0u);
}

// 5) 混合查询："的 苹果" -> 过滤停用词后命中含 "苹果" 的文档
TEST(StopwordEdgeV015, MixedQuery_FilterStopwordThenHit) {
    TempDir tmp;
    tmp.writeDoc("apple.txt", "苹果 香蕉 橙子");

    docseek::Index index;
    buildIndex(index, {tmp.path() / "apple.txt"});

    auto results = index.search("的 苹果");
    ASSERT_EQ(results.size(), 1u);
}

// 6) 多字 token 不受影响：doc "我的苹果"，query "我的" -> 命中
//    （"我的" 非单字停用词，不拆分为 "我" + "的"）
TEST(StopwordEdgeV015, MultiCharToken_NotSplit_ReturnsHit) {
    TempDir tmp;
    tmp.writeDoc("a.txt", "我的苹果 很甜");

    docseek::Index index;
    buildIndex(index, {tmp.path() / "a.txt"});

    auto results = index.search("我的");
    ASSERT_EQ(results.size(), 1u);
}

// 7) 否定保护："不" 不在停用词表；doc "不建议熬夜"，query "不建议" -> 命中
TEST(StopwordEdgeV015, Negation_NotInStopwordList_ReturnsHit) {
    TempDir tmp;
    tmp.writeDoc("a.txt", "不建议熬夜 注意身体");

    docseek::Index index;
    buildIndex(index, {tmp.path() / "a.txt"});

    auto results = index.search("不建议");
    ASSERT_EQ(results.size(), 1u);
}

// 8) 空格变形："  的   " -> 0 hits（trim 后仍是纯停用词）
TEST(StopwordEdgeV015, WhitespaceVariants_PureStopword_ReturnsZeroHits) {
    TempDir tmp;
    tmp.writeDoc("a.txt", "苹果 香蕉 橙子");

    docseek::Index index;
    buildIndex(index, {tmp.path() / "a.txt"});

    auto results = index.search("  的   ");
    EXPECT_EQ(results.size(), 0u);
}

// 9) searchQuestion 同样过滤：query "的" -> 0 hits
TEST(StopwordEdgeV015, SearchQuestion_PureStopword_ReturnsZeroHits) {
    TempDir tmp;
    tmp.writeDoc("a.txt", "苹果 香蕉 橙子");

    docseek::Index index;
    buildIndex(index, {tmp.path() / "a.txt"});

    auto results = index.searchQuestion("的");
    EXPECT_EQ(results.size(), 0u);
}

// 10) 短语豁免：query "\"的\""（引号短语）走纯短语分支，doc 含 "的" 则命中。
//     保守断言：doc "这是的测试" query "\"的\"" -> 1 hit。
TEST(StopwordEdgeV015, QuotedPhrase_StopwordChar_StillHits) {
    TempDir tmp;
    tmp.writeDoc("a.txt", "这是的测试 内容");

    docseek::Index index;
    buildIndex(index, {tmp.path() / "a.txt"});

    auto results = index.search("\"的\"");
    ASSERT_EQ(results.size(), 1u);
}

// 11) 短语豁免与普通 search 行为一致：同一 doc 分别用引号短语与普通查询，
//     至少保证不崩溃，且引号短语不因停用词被静默丢弃。
TEST(StopwordEdgeV015, QuotedPhrase_DoesNotCrash_AndConsistentWithSearch) {
    TempDir tmp;
    tmp.writeDoc("a.txt", "这是的测试 内容");

    docseek::Index index;
    buildIndex(index, {tmp.path() / "a.txt"});

    // 不应崩溃。
    auto phraseResults = index.search("\"的\"");
    auto plainResults = index.search("的");

    // 引号短语走纯短语分支，普通 "的" 走停用词过滤分支。
    // 保守断言：两者均不崩溃；且引号短语不应被停用词过滤为 0。
    EXPECT_EQ(plainResults.size(), 0u);
    EXPECT_EQ(phraseResults.size(), 1u);
}

// 12) 混合查询中的多字 token 不受影响：query "我的 苹果" -> 命中
TEST(StopwordEdgeV015, MixedQuery_MultiCharTokenPreserved) {
    TempDir tmp;
    tmp.writeDoc("a.txt", "我的苹果 很甜");

    docseek::Index index;
    buildIndex(index, {tmp.path() / "a.txt"});

    auto results = index.search("我的 苹果");
    ASSERT_EQ(results.size(), 1u);
}

}  // namespace
