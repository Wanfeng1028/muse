#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/bigram_tokenizer.h"

#include <sqlite3.h>

#include <string>
#include <vector>

// 事实来源: include/docseek/bigram_tokenizer.h
// 声明的查询侧切分接口:
//   std::vector<std::string> bigramCutForSearch(const std::string& text);
// 本文件仅依据该头文件声明进行调用, 不引用任何未声明 API。

namespace {

// 直接调用 bigram 查询侧切分接口。签名与头文件逐字一致:
//   std::vector<std::string> docseek::bigramCutForSearch(const std::string& text);
std::vector<std::string> bigramCut(const std::string& text) {
    return docseek::bigramCutForSearch(text);
}

}  // namespace

// 头文件声明的切分函数对 "全文检索" 输出非空。
TEST(BigramTokenizerR2, FullTextSearchNonEmpty) {
    std::vector<std::string> tokens = bigramCut("全文检索");
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
}

// 空串输入不抛异常。
TEST(BigramTokenizerR2, EmptyInputNoThrow) {
    std::vector<std::string> tokens;
    EXPECT_NO_THROW(tokens = bigramCut(""));
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
}

// 单字输入不抛异常。
TEST(BigramTokenizerR2, SingleCharNoThrow) {
    std::vector<std::string> tokens;
    EXPECT_NO_THROW(tokens = bigramCut("文"));
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
}

// 纯 ASCII 输入不抛异常。
TEST(BigramTokenizerR2, PureAsciiNoThrow) {
    std::vector<std::string> tokens;
    EXPECT_NO_THROW(tokens = bigramCut("hello world 123"));
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
}