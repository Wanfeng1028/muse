// tests/test_html_entities.cpp
// 用途：验证 docseek::HtmlExtractor 对 HTML 实体（命名实体、十进制/十六进制数字实体、
//       非法实体保留、大小写不敏感、title 中解码等）的真实解码行为。

#include <gtest/gtest.h>

#include <string>

#include "docseek/html_extractor.h"

namespace {

using docseek::HtmlExtracted;
using docseek::HtmlExtractor;

// 1. 基础命名实体：&amp; &lt; &gt; &quot; &apos; &nbsp;
//    nbsp 解码为空格，为避免被 trim，放在中间：a&nbsp;b -> "a b"
TEST(HtmlEntities, NamedBasic) {
    const HtmlExtracted r =
        HtmlExtractor::extract("<p>&amp;&lt;&gt;&quot;&apos;</p>");
    EXPECT_EQ(r.text, "&<>\"'");

    const HtmlExtracted r2 = HtmlExtractor::extract("<p>a&nbsp;b</p>");
    EXPECT_EQ(r2.text, "a b");
}

// 2. 扩展命名实体：&copy; &mdash; &hellip; &euro; &laquo; &raquo;
TEST(HtmlEntities, NamedExtended) {
    const HtmlExtracted r = HtmlExtractor::extract(
        "<p>&copy;&mdash;&hellip;&euro;&laquo;&raquo;</p>");
    EXPECT_EQ(r.text, "©—…€«»");
}

// 3. 十进制数字实体
TEST(HtmlEntities, DecimalEntity) {
    const HtmlExtracted r = HtmlExtractor::extract("<p>&#65;&#66;</p>");
    EXPECT_EQ(r.text, "AB");
}

// 4. 十六进制数字实体（含小写 x 与大写 X）
TEST(HtmlEntities, HexEntity) {
    const HtmlExtracted r = HtmlExtractor::extract("<p>&#x4E2D;&#X6587;</p>");
    EXPECT_EQ(r.text, "中文");
}

// 5. 非法实体与缺分号实体原样保留
TEST(HtmlEntities, InvalidKept) {
    const HtmlExtracted r = HtmlExtractor::extract("<p>&foobar;&amp</p>");
    EXPECT_EQ(r.text, "&foobar;&amp");
}

// 6. 命名实体大小写不敏感
TEST(HtmlEntities, CaseInsensitive) {
    const HtmlExtracted r = HtmlExtractor::extract("<p>&AMP;&LT;</p>");
    EXPECT_EQ(r.text, "&<");
}

// 7. title 中的实体同样解码
TEST(HtmlEntities, InTitle) {
    const HtmlExtracted r = HtmlExtractor::extract("<title>a&amp;b</title>");
    EXPECT_EQ(r.title, "a&b");
}

// 8. 属性中的实体不进入正文，正文仅为链接文本 "t"
TEST(HtmlEntities, NumericInAttrIgnored) {
    const HtmlExtracted r =
        HtmlExtractor::extract("<a href=\"?x=1&amp;y=2\">t</a>");
    EXPECT_EQ(r.text, "t");
}

}  // namespace
