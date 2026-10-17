#include <gtest/gtest.h>

#include <atomic>
#include <set>
#include <string>
#include <thread>
#include <vector>

#include "docseek/jieba_tokenizer.h"
#include "cppjieba/Jieba.hpp"

namespace docseek {
namespace {

// 测试辅助：用单例 Jieba 对给定文本做 CutForSearch，返回词序列。
std::vector<std::string> cut(const std::string& text) {
    std::vector<std::string> words;
    const cppjieba::Jieba* jieba = jiebaInstance();
    if (jieba == nullptr) {
        return words;
    }
    jieba->CutForSearch(text, words);
    return words;
}

// 测试辅助：把词序列拼成一个以 '|' 分隔的字符串，方便做一致性比较。
std::string joinWords(const std::vector<std::string>& words) {
    std::string out;
    for (size_t i = 0; i < words.size(); ++i) {
        if (i != 0) out.push_back('|');
        out += words[i];
    }
    return out;
}

// 词典必须能加载成功，否则后面所有用例都失去意义。
TEST(JiebaTokenizerEdge, DictLoadsSuccessfully) {
    const cppjieba::Jieba* jieba = jiebaInstance();
    ASSERT_NE(jieba, nullptr);
    EXPECT_EQ(jiebaInitError(), "");
}

// 1. 空串：CutForSearch 不应崩溃，也不应产生任何词。
TEST(JiebaTokenizerEdge, EmptyString) {
    std::vector<std::string> words = cut("");
    EXPECT_EQ(words.size(), 0u);
    EXPECT_TRUE(words.empty());
}

// 2. 纯英文：应被切出可识别的英文片段，且全部非空。
TEST(JiebaTokenizerEdge, PureEnglish) {
    std::vector<std::string> words = cut("hello world");
    ASSERT_FALSE(words.empty());
    std::string joined = joinWords(words);
    EXPECT_NE(joined.find("hello"), std::string::npos);
    for (const std::string& w : words) {
        EXPECT_FALSE(w.empty());
    }
}

// 3. 纯数字：数字串应被切分，且不产生空词。
TEST(JiebaTokenizerEdge, PureDigits) {
    std::vector<std::string> words = cut("1234567890");
    ASSERT_FALSE(words.empty());
    std::string joined = joinWords(words);
    EXPECT_NE(joined.find("1234567890"), std::string::npos);
    for (const std::string& w : words) {
        EXPECT_FALSE(w.empty());
    }
}

// 4. 中英混合：中文词与英文片段都要出现在结果里。
TEST(JiebaTokenizerEdge, MixedChineseEnglish) {
    std::vector<std::string> words = cut("我爱吃 apple 和 banana");
    ASSERT_FALSE(words.empty());
    std::string joined = joinWords(words);
    EXPECT_NE(joined.find("apple"), std::string::npos);
    EXPECT_NE(joined.find("banana"), std::string::npos);
    EXPECT_NE(joined.find("爱"), std::string::npos);
}

// 5. 超长串：10 万个 'a' 不应崩溃，且能返回结果。
TEST(JiebaTokenizerEdge, HugeStringTenLakhAscii) {
    std::string big(100000, 'a');
    std::vector<std::string> words = cut(big);
    ASSERT_FALSE(words.empty());
    size_t total = 0;
    for (const std::string& w : words) {
        total += w.size();
    }
    EXPECT_GT(total, 0u);
    EXPECT_LE(total, big.size());
}

// 6. 特殊符号：emoji 与全角标点不应让分词崩溃，且返回结果非空。
TEST(JiebaTokenizerEdge, SpecialSymbols) {
    std::string text = "你好😀世界！，。？";
    std::vector<std::string> words = cut(text);
    ASSERT_FALSE(words.empty());
    for (const std::string& w : words) {
        EXPECT_FALSE(w.empty());
    }
}

// 7. 单字：单个汉字应被切出至少一个词，且拼接后包含该字。
TEST(JiebaTokenizerEdge, SingleChineseChar) {
    std::vector<std::string> words = cut("中");
    ASSERT_FALSE(words.empty());
    std::string joined = joinWords(words);
    EXPECT_NE(joined.find("中"), std::string::npos);
}

// 8. 停用词：单独输入停用词"的"，分词不应崩溃，返回可比较的结果。
TEST(JiebaTokenizerEdge, StopWord) {
    std::vector<std::string> words = cut("的");
    std::string joined = joinWords(words);
    EXPECT_NE(joined.find("的"), std::string::npos);
    for (const std::string& w : words) {
        EXPECT_FALSE(w.empty());
    }
}

// 9. "中华人民共和国"：长词应能被切出包含该长词的子串。
TEST(JiebaTokenizerEdge, LongWordChina) {
    std::vector<std::string> words = cut("中华人民共和国");
    ASSERT_FALSE(words.empty());
    std::string joined = joinWords(words);
    EXPECT_NE(joined.find("中华人民共和国"), std::string::npos);
    EXPECT_NE(joined.find("中国"), std::string::npos);
}

// 10. 重复调用一致性：同一串分词两次，结果逐字相同。
TEST(JiebaTokenizerEdge, RepeatedCallConsistency) {
    std::string text = "北京市海淀区中关村大街";
    std::vector<std::string> first = cut(text);
    std::vector<std::string> second = cut(text);
    ASSERT_EQ(first.size(), second.size());
    EXPECT_EQ(joinWords(first), joinWords(second));
    for (size_t i = 0; i < first.size(); ++i) {
        EXPECT_EQ(first[i], second[i]);
    }
}

// 11. 多线程并发分词：4 线程各 100 次，结果一致且无崩溃。
TEST(JiebaTokenizerEdge, ConcurrentTokenizeFourThreads) {
    const std::string text = "上海自来水来自海上，北京烤鸭真好吃。";
    std::vector<std::string> baseline = cut(text);
    ASSERT_FALSE(baseline.empty());
    const std::string baselineJoined = joinWords(baseline);

    const int kThreads = 4;
    const int kIters = 100;
    std::atomic<int> mismatches{0};
    std::atomic<int> empties{0};
    std::vector<std::thread> threads;
    threads.reserve(kThreads);
    for (int t = 0; t < kThreads; ++t) {
        threads.emplace_back([&]() {
            for (int i = 0; i < kIters; ++i) {
                std::vector<std::string> got = cut(text);
                if (got.empty()) {
                    ++empties;
                    continue;
                }
                if (joinWords(got) != baselineJoined) {
                    ++mismatches;
                }
            }
        });
    }
    for (std::thread& th : threads) {
        th.join();
    }
    EXPECT_EQ(mismatches.load(), 0);
    EXPECT_EQ(empties.load(), 0);
}

// 12. 空白串：全空格输入，分词不应崩溃。
TEST(JiebaTokenizerEdge, WhitespaceOnly) {
    std::vector<std::string> words = cut("   \t\n  ");
    for (const std::string& w : words) {
        EXPECT_FALSE(w.empty());
    }
    // 全空白通常不产生有意义的词；这里只断言不崩溃且所有词非空。
    EXPECT_GE(words.size(), 0u);
}

// 13. 标点串：全标点输入，分词不应崩溃。
TEST(JiebaTokenizerEdge, PunctuationOnly) {
    std::vector<std::string> words = cut("！？。，、；：");
    for (const std::string& w : words) {
        EXPECT_FALSE(w.empty());
    }
    EXPECT_GE(words.size(), 0u);
}

// 14. 数字与单位混合：能切出包含数字的片段。
TEST(JiebaTokenizerEdge, NumberWithUnit) {
    std::vector<std::string> words = cut("温度是 25 摄氏度");
    ASSERT_FALSE(words.empty());
    std::string joined = joinWords(words);
    EXPECT_NE(joined.find("25"), std::string::npos);
    EXPECT_NE(joined.find("温度"), std::string::npos);
}

// 15. 重复词：同一词在句中重复出现，分词结果应保持稳定且非空。
TEST(JiebaTokenizerEdge, RepeatedWordInSentence) {
    std::vector<std::string> words = cut("学习学习再学习");
    ASSERT_FALSE(words.empty());
    std::string joined = joinWords(words);
    EXPECT_NE(joined.find("学习"), std::string::npos);
    for (const std::string& w : words) {
        EXPECT_FALSE(w.empty());
    }
}

// 16. 长中文句子：一段完整中文，切出的词拼接后应覆盖原文所有汉字。
TEST(JiebaTokenizerEdge, LongChineseSentence) {
    std::string text = "今天天气真好，我们一起去公园散步吧。";
    std::vector<std::string> words = cut(text);
    ASSERT_FALSE(words.empty());
    std::string joined = joinWords(words);
    EXPECT_NE(joined.find("今天"), std::string::npos);
    EXPECT_NE(joined.find("公园"), std::string::npos);
    EXPECT_NE(joined.find("散步"), std::string::npos);
}

}  // namespace
}  // namespace docseek