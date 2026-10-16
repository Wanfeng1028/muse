#include <gtest/gtest.h>

#include <string>

#include "docseek/html_extractor.h"

// 本文件用于验证 docseek::HtmlExtractor 的字符集检测与字节解码行为：
// - detectCharset 的 BOM / meta charset / meta http-equiv / 默认回退规则
// - gbk、gb2312 规范化为 GB18030
// - extractFromBytes 在已知与未知字符集下的成功/失败语义
// 全部使用真实 GBK / UTF-16LE 字节序列进行断言。

namespace {

// 直接拼接真实 GBK 编码字节，避免依赖源文件编码。
const char* const kGbkCeShi = "\xB2\xE2\xCA\xD4";                    // 测试
const char* const kGbkZhongWenXinWen = "\xD6\xD0\xCE\xC4\xD0\xC2\xCE\xC5";  // 中文新闻
const char* const kGbkZhongWen = "\xD6\xD0\xCE\xC4";                  // 中文

}  // namespace

// 1. UTF-8 BOM 前缀：检测为 UTF-8，且正文解析正常。
TEST(HtmlCharset, Utf8Bom) {
    const std::string raw =
        std::string("\xEF\xBB\xBF", 3) + "<title>T</title><p>正文</p>";

    EXPECT_EQ(docseek::HtmlExtractor::detectCharset(raw), "UTF-8");

    const docseek::HtmlExtractResult result =
        docseek::HtmlExtractor::extractFromBytes(raw);
    EXPECT_TRUE(result.ok);
    EXPECT_EQ(result.doc.title, "T");
    EXPECT_EQ(result.doc.text, "正文");
}

// 2. <meta charset="gbk">：规范化 GB18030，并按 GBK 字节解码标题与正文。
TEST(HtmlCharset, MetaGbk) {
    const std::string raw =
        std::string("<html><head><meta charset=\"gbk\"><title>") + kGbkCeShi +
        "</title></head><body><p>" + kGbkZhongWenXinWen + "</p></body></html>";

    EXPECT_EQ(docseek::HtmlExtractor::detectCharset(raw), "GB18030");

    const docseek::HtmlExtractResult result =
        docseek::HtmlExtractor::extractFromBytes(raw);
    EXPECT_TRUE(result.ok);
    EXPECT_EQ(result.doc.title, "测试");
    EXPECT_EQ(result.doc.text, "中文新闻");
}

// 3. <meta http-equiv="Content-Type" content="text/html; charset=GB2312">：
//    usedCharset 规范化为 GB18030，正文按 GBK 字节解码。
TEST(HtmlCharset, MetaHttpEquiv) {
    const std::string raw =
        std::string("<html><head><meta http-equiv=\"Content-Type\" "
                    "content=\"text/html; charset=GB2312\"></head><body><p>") +
        kGbkZhongWen + "</p></body></html>";

    const docseek::HtmlExtractResult result =
        docseek::HtmlExtractor::extractFromBytes(raw);
    EXPECT_TRUE(result.ok);
    EXPECT_EQ(result.usedCharset, "GB18030");
    EXPECT_EQ(result.doc.text, "中文");
}

// 4. 无 meta 的纯 UTF-8 中文：默认 UTF-8，正文解析正常。
TEST(HtmlCharset, DefaultUtf8) {
    const std::string raw = "<p>纯中文无meta</p>";

    EXPECT_EQ(docseek::HtmlExtractor::detectCharset(raw), "UTF-8");

    const docseek::HtmlExtractResult result =
        docseek::HtmlExtractor::extractFromBytes(raw);
    EXPECT_TRUE(result.ok);
    EXPECT_EQ(result.doc.text, "纯中文无meta");
}

// 5. UTF-16LE BOM：检测为 UTF-16LE，且能解码 <title>AB</title>。
// 注意：字节串含 NUL，必须用 char 数组 + 显式长度构造，字符串字面量会在 \x00 处截断。
TEST(HtmlCharset, Utf16Le) {
    const char kBody[] = {
        '\x3C','\x00','\x74','\x00','\x69','\x00','\x74','\x00','\x6C','\x00','\x65','\x00','\x3E','\x00',  // <title>
        '\x41','\x00','\x42','\x00',                                                                    // AB
        '\x3C','\x00','\x2F','\x00','\x74','\x00','\x69','\x00','\x74','\x00','\x6C','\x00','\x65','\x00','\x3E','\x00'  // </title>
    };
    const std::string raw =
        std::string("\xFF\xFE", 2) + std::string(kBody, sizeof(kBody));

    EXPECT_EQ(docseek::HtmlExtractor::detectCharset(raw), "UTF-16LE");

    const docseek::HtmlExtractResult result =
        docseek::HtmlExtractor::extractFromBytes(raw);
    EXPECT_TRUE(result.ok);
    EXPECT_EQ(result.doc.title, "AB");
}

// 6. 未知 charset：iconv 无法打开该编码，extractFromBytes 返回 ok=false。
TEST(HtmlCharset, UnknownCharset) {
    const std::string raw = "<meta charset=\"x-unknown-zzz\"><p>hi</p>";

    const docseek::HtmlExtractResult result =
        docseek::HtmlExtractor::extractFromBytes(raw);
    EXPECT_FALSE(result.ok);
}

// 7. 大写标签与属性名：仍应识别 <META CHARSET="GBK"> 并规范化为 GB18030。
TEST(HtmlCharset, UppercaseMeta) {
    const std::string raw =
        std::string("<HTML><HEAD><META CHARSET=\"GBK\"></HEAD><BODY><P>") +
        kGbkZhongWen + "</P></BODY></HTML>";

    EXPECT_EQ(docseek::HtmlExtractor::detectCharset(raw), "GB18030");
}
