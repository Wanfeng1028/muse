#include "docseek/html_extractor.h"

#include <cerrno>
#include <cstdint>
#include <cstring>
#include <iconv.h>
#include <string>
#include <vector>

namespace docseek {
namespace {

bool isAsciiAlpha(char c) {
return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
}

bool isNameChar(char c) {
return isAsciiAlpha(c) || (c >= '0' && c <= '9') || c == '-' || c == '_' || c == ':';
}

char toLowerAscii(char c) {
if (c >= 'A' && c <= 'Z') return static_cast<char>(c - 'A' + 'a');
return c;
}

std::string toLower(const std::string& s) {
std::string r;
r.reserve(s.size());
for (char c : s) r.push_back(toLowerAscii(c));
return r;
}

bool isSpaceChar(char c) {
return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v';
}

bool isBlockTag(const std::string& name) {
static const char* kBlocks[] = {
"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "br", "li", "ul", "ol",
"dl", "dt", "dd", "table", "tr", "td", "th", "thead", "tbody",
"blockquote", "pre", "section", "article", "header", "footer", "nav",
"aside", "main", "hr"};
for (const char* b : kBlocks) {
if (name == b) return true;
}
return false;
}

void appendUtf8(std::string& out, uint32_t cp) {
if (cp <= 0x7F) {
out.push_back(static_cast<char>(cp));
} else if (cp <= 0x7FF) {
out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
} else if (cp <= 0xFFFF) {
out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
} else if (cp <= 0x10FFFF) {
out.push_back(static_cast<char>(0xF0 | (cp >> 18)));
out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
}
}

bool isValidCodePoint(uint32_t cp) {
if (cp == 0) return false;
if (cp > 0x10FFFF) return false;
if (cp >= 0xD800 && cp <= 0xDFFF) return false;
return true;
}

bool decodeEntity(const std::string& html, size_t pos, size_t& consumed, std::string& out) {
// pos 指向 '&' 之后。返回 true 表示成功识别并消费。
size_t p = pos;
if (p >= html.size()) return false;
if (html[p] == '#') {
++p;
if (p >= html.size()) return false;
bool hex = false;
if (html[p] == 'x' || html[p] == 'X') {
hex = true;
++p;
}
size_t start = p;
uint32_t cp = 0;
bool any = false;
while (p < html.size()) {
char c = html[p];
uint32_t d = 0;
if (c >= '0' && c <= '9') d = static_cast<uint32_t>(c - '0');
else if (hex && c >= 'a' && c <= 'f') d = static_cast<uint32_t>(c - 'a' + 10);
else if (hex && c >= 'A' && c <= 'F') d = static_cast<uint32_t>(c - 'A' + 10);
else break;
cp = cp * (hex ? 16u : 10u) + d;
if (cp > 0x10FFFF) cp = 0x110000; // 溢出保护
any = true;
++p;
}
if (!any || p == start) return false;
if (p < html.size() && html[p] == ';') {
++p;
consumed = p - pos;
if (isValidCodePoint(cp)) {
appendUtf8(out, cp);
} 
return true;
}
return false;
}
// 命名实体
size_t start = p;
while (p < html.size() && p - start < 32 && isAsciiAlpha(html[p])) {
++p;
}
if (p == start) return false;
std::string name = html.substr(start, p - start);
bool hasSemi = false;
if (p < html.size() && html[p] == ';') {
hasSemi = true;
++p;
}
std::string lower = toLower(name);
if (!hasSemi) return false;

// 命名实体表：{名字, 码点}，码点 0 表示"输出单字节 ASCII 字符"的特例（此处不使用）。
// 查找前已 toLower，故表中名字全部小写即可实现大小写不敏感。
static const struct { const char* name; char32_t cp; } kNamed[] = {
    {"amp",    U'&'},        // & 与号
    {"lt",     U'<'},        // < 小于号
    {"gt",     U'>'},        // > 大于号
    {"quot",   U'"'},        // " 双引号
    {"apos",   U'\''},       // ' 单引号
    {"nbsp",   U' '},        // 不换行空格（保持原有行为：输出普通空格）
    {"copy",   0x00A9u},     // © 版权
    {"reg",    0x00AEu},     // ® 注册商标
    {"trade",  0x2122u},     // ™ 商标
    {"hellip", 0x2026u},     // … 省略号
    {"mdash",  0x2014u},     // — 长破折号
    {"ndash",  0x2013u},     // – 短破折号
    {"laquo",  0x00ABu},     // « 左双角引号
    {"raquo",  0x00BBu},     // » 右双角引号
    {"ldquo",  0x201Cu},     // “ 左双引号
    {"rdquo",  0x201Du},     // ” 右双引号
    {"lsquo",  0x2018u},     // ‘ 左单引号
    {"rsquo",  0x2019u},     // ’ 右单引号
    {"sbquo",  0x201Au},     // ‚ 低左单引号
    {"bdquo",  0x201Eu},     // „ 低左双引号
    {"euro",   0x20ACu},     // € 欧元
    {"pound",  0x00A3u},     // £ 英镑
    {"yen",    0x00A5u},     // ¥ 日元
    {"cent",   0x00A2u},     // ¢ 分
    {"sect",   0x00A7u},     // § 节
    {"para",   0x00B6u},     // ¶ 段落
    {"middot", 0x00B7u},     // · 中间点
    {"bull",   0x2022u},     // • 圆点
    {"times",  0x00D7u},     // × 乘号
    {"divide", 0x00F7u},     // ÷ 除号
    {"plusmn", 0x00B1u},     // ± 正负号
    {"deg",    0x00B0u},     // ° 度
    {"micro",  0x00B5u},     // µ 微
    {"sup1",   0x00B9u},     // ¹ 上标 1
    {"sup2",   0x00B2u},     // ² 上标 2
    {"sup3",   0x00B3u},     // ³ 上标 3
    {"frac14", 0x00BCu},     // ¼ 四分之一
    {"frac12", 0x00BDu},     // ½ 二分之一
    {"frac34", 0x00BEu},     // ¾ 四分之三
    {"iexcl",  0x00A1u},     // ¡ 倒感叹号
    {"iquest", 0x00BFu},     // ¿ 倒问号
    {"brvbar", 0x00A6u},     // ¦ 断竖线
    {"curren", 0x00A4u},     // ¤ 货币符
    {"szlig",  0x00DFu},     // ß 德语 eszett
    {"ordf",   0x00AAu},     // ª 阴性序数
    {"ordm",   0x00BAu},     // º 阳性序数
};

for (const auto& e : kNamed) {
    if (lower == e.name) {
        appendUtf8(out, static_cast<char32_t>(e.cp));
        consumed = p - pos;
        return true;
    }
}
return false;

}

struct RawBuilder {
std::string out;
bool pendingSpace = false;
int pendingNewlines = 0;
bool hasContent = false;

void addSpace() {
if (!hasContent) return;
if (pendingNewlines > 0) return;
pendingSpace = true;
}

void addNewline() {
if (!hasContent) return;
if (pendingNewlines < 2) ++pendingNewlines;
pendingSpace = false;
}

void flushPending() {
if (!hasContent) return;
if (pendingNewlines > 0) {
out.append(static_cast<size_t>(pendingNewlines), '\n');
pendingNewlines = 0;
pendingSpace = false;
} else if (pendingSpace) {
out.push_back(' ');
pendingSpace = false;
}
}

void addChar(char c) {
if (isSpaceChar(c)) {
addSpace();
return;
}
flushPending();
out.push_back(c);
hasContent = true;
}

void addString(const std::string& s) {
for (char c : s) addChar(c);
}

std::string finalize() {
std::string result = out;
while (!result.empty() && (result.back() == ' ' || result.back() == '\n')) {
result.pop_back();
}
return result;
}
};

} // namespace

std::string HtmlExtractor::detectCharset(const std::string& rawBytes) {
    // BOM 优先判定
    if (rawBytes.size() >= 3 &&
        static_cast<unsigned char>(rawBytes[0]) == 0xEF &&
        static_cast<unsigned char>(rawBytes[1]) == 0xBB &&
        static_cast<unsigned char>(rawBytes[2]) == 0xBF) {
        return "UTF-8";
    }
    if (rawBytes.size() >= 2) {
        unsigned char b0 = static_cast<unsigned char>(rawBytes[0]);
        unsigned char b1 = static_cast<unsigned char>(rawBytes[1]);
        if (b0 == 0xFF && b1 == 0xFE) return "UTF-16LE";
        if (b0 == 0xFE && b1 == 0xFF) return "UTF-16BE";
    }

    // 只扫描前 8192 字节
    const std::size_t kScanLimit = 8192;
    std::string head = rawBytes.substr(0, kScanLimit);
    std::string low = toLower(head);

    // 规范化映射表
    auto normalize = [](const std::string& raw) -> std::string {
        // 去掉首尾引号与空白
        std::size_t b = 0;
        std::size_t e = raw.size();
        while (b < e && (isSpaceChar(raw[b]) || raw[b] == '"' || raw[b] == '\'')) ++b;
        while (e > b && (isSpaceChar(raw[e - 1]) || raw[e - 1] == '"' || raw[e - 1] == '\'')) --e;
        std::string v = toLower(raw.substr(b, e - b));
        if (v.empty()) return std::string();
        if (v == "utf-8" || v == "utf8") return "UTF-8";
        if (v == "gbk" || v == "gb2312" || v == "gb18030") return "GB18030";
        if (v == "big5") return "BIG5";
        if (v == "iso-8859-1" || v == "latin1" || v == "windows-1252") return "WINDOWS-1252";
        if (v == "utf-16" || v == "utf-16le") return "UTF-16LE";
        if (v == "utf-16be") return "UTF-16BE";
        // 未知值：转大写原样返回
        std::string up;
        up.reserve(v.size());
        for (char c : v) {
            if (c >= 'a' && c <= 'z') up.push_back(static_cast<char>(c - 'a' + 'A'));
            else up.push_back(c);
        }
        return up;
    };

    // 从值起始位置向后读，遇到引号/空白/'>' 停止
    auto readValue = [&](const std::string& src, std::size_t pos) -> std::string {
        std::size_t b = pos;
        while (b < src.size() && isSpaceChar(src[b])) ++b;
        if (b < src.size() && (src[b] == '"' || src[b] == '\'')) {
            char q = src[b];
            ++b;
            std::size_t e = b;
            while (e < src.size() && src[e] != q) ++e;
            return src.substr(b, e - b);
        }
        std::size_t e = b;
        while (e < src.size() && !isSpaceChar(src[e]) && src[e] != '>' && src[e] != '/') ++e;
        return src.substr(b, e - b);
    };

    const std::size_t n = low.size();
    std::size_t i = 0;
    while (i < n) {
        // 在 </head> 或 <body 处停止
        if (low.compare(i, 7, "</head>") == 0) break;
        if (low.compare(i, 5, "<body") == 0 &&
            (i + 5 == n || isSpaceChar(low[i + 5]) || low[i + 5] == '>' || low[i + 5] == '/')) {
            break;
        }

        if (low[i] != '<') {
            ++i;
            continue;
        }

        // 判定 <meta 起始
        if (low.compare(i, 5, "<meta") != 0) {
            ++i;
            continue;
        }
        std::size_t after = i + 5;
        if (after < n && !isSpaceChar(low[after]) && low[after] != '>' && low[after] != '/') {
            ++i;
            continue;
        }

        // 找到 meta 标签结束位置 '>'
        std::size_t tagEnd = after;
        while (tagEnd < n && low[tagEnd] != '>') ++tagEnd;
        if (tagEnd >= n) break; // 前 8KB 内没找到完整标签

        const std::size_t tagBegin = i;
        const std::size_t tagBodyLen = tagEnd - tagBegin + 1;

        // 优先看 charset= 形式（属性名 "charset"）
        // 在 meta 标签内查找 "charset"
        std::size_t p = after;
        bool found = false;
        std::string result;
        while (p < tagEnd) {
            // 找 "charset"
            if (low.compare(p, 7, "charset") == 0) {
                // 前一个字符必须是分隔符（空白或标签名后紧跟）
                bool leftOk = (p == after) || isSpaceChar(low[p - 1]) ||
                              low[p - 1] == '"' || low[p - 1] == '\'' ||
                              low[p - 1] == '/';
                if (leftOk) {
                    std::size_t q = p + 7;
                    while (q < tagEnd && isSpaceChar(low[q])) ++q;
                    if (q < tagEnd && low[q] == '=') {
                        ++q;
                        std::string val = readValue(low, q);
                        if (!val.empty()) {
                            std::string norm = normalize(val);
                            if (!norm.empty()) {
                                result = norm;
                                found = true;
                                break;
                            }
                        }
                    }
                }
            }
            ++p;
        }

        if (!found) {
            // 其次看 content 属性里是否包含 "charset="
            std::size_t c = after;
            while (c < tagEnd) {
                if (low.compare(c, 7, "content") == 0) {
                    bool leftOk = (c == after) || isSpaceChar(low[c - 1]) ||
                                  low[c - 1] == '"' || low[c - 1] == '\'' ||
                                  low[c - 1] == '/';
                    if (leftOk) {
                        std::size_t q = c + 7;
                        while (q < tagEnd && isSpaceChar(low[q])) ++q;
                        if (q < tagEnd && low[q] == '=') {
                            ++q;
                            std::string contentVal = readValue(low, q);
                            std::string contentLow = toLower(contentVal);
                            std::size_t cs = contentLow.find("charset");
                            if (cs != std::string::npos) {
                                std::size_t k = cs + 7;
                                while (k < contentLow.size() && isSpaceChar(contentLow[k])) ++k;
                                if (k < contentLow.size() && contentLow[k] == '=') {
                                    ++k;
                                    std::string v = readValue(contentLow, k);
                                    std::string norm = normalize(v);
                                    if (!norm.empty()) {
                                        result = norm;
                                        found = true;
                                        break;
                                    }
                                }
                            }
                        }
                    }
                }
                ++c;
            }
        }

        if (found) return result;

        i = tagEnd + 1;
        (void)tagBodyLen;
    }

    return "UTF-8";
}

std::string HtmlExtractor::decodeToUtf8(const std::string& rawBytes, const std::string& charset) {
    // 空输入直接返回空串
    if (rawBytes.empty()) return std::string();

    // UTF-8 的 BOM 不属于正文，先剥离（UTF-16 的 BOM 由分支内处理）
    std::string input = rawBytes;
    if (charset == "UTF-8" && input.size() >= 3 &&
        static_cast<unsigned char>(input[0]) == 0xEF &&
        static_cast<unsigned char>(input[1]) == 0xBB &&
        static_cast<unsigned char>(input[2]) == 0xBF) {
        input = input.substr(3);
        if (input.empty()) return std::string();
    }
    const std::string& src = input;

    try {
        std::string out;
        out.reserve(src.size());

        if (charset == "UTF-16LE" || charset == "UTF-16BE") {
            const bool le = (charset == "UTF-16LE");
            std::size_t i = 0;
            const std::size_t n = src.size();

            // 跳过开头的 BOM
            if (n >= 2) {
                const unsigned char b0 = static_cast<unsigned char>(src[0]);
                const unsigned char b1 = static_cast<unsigned char>(src[1]);
                if (le && b0 == 0xFF && b1 == 0xFE) {
                    i = 2;
                } else if (!le && b0 == 0xFE && b1 == 0xFF) {
                    i = 2;
                }
            }

            while (i + 1 < n) {
                const unsigned char b0 = static_cast<unsigned char>(src[i]);
                const unsigned char b1 = static_cast<unsigned char>(src[i + 1]);
                i += 2;
                const std::uint32_t unit = le
                    ? (static_cast<std::uint32_t>(b0) | (static_cast<std::uint32_t>(b1) << 8))
                    : ((static_cast<std::uint32_t>(b0) << 8) | static_cast<std::uint32_t>(b1));

                if (unit >= 0xD800 && unit <= 0xDBFF) {
                    // 高代理项：需要后跟低代理项
                    if (i + 1 < n) {
                        const unsigned char c0 = static_cast<unsigned char>(src[i]);
                        const unsigned char c1 = static_cast<unsigned char>(src[i + 1]);
                        const std::uint32_t next = le
                            ? (static_cast<std::uint32_t>(c0) | (static_cast<std::uint32_t>(c1) << 8))
                            : ((static_cast<std::uint32_t>(c0) << 8) | static_cast<std::uint32_t>(c1));
                        if (next >= 0xDC00 && next <= 0xDFFF) {
                            i += 2;
                            const std::uint32_t cp =
                                0x10000u + ((unit - 0xD800u) << 10) + (next - 0xDC00u);
                            appendUtf8(out, cp);
                            continue;
                        }
                    }
                    appendUtf8(out, 0xFFFD);
                } else if (unit >= 0xDC00 && unit <= 0xDFFF) {
                    // 孤立低代理项
                    appendUtf8(out, 0xFFFD);
                } else {
                    appendUtf8(out, unit);
                }
            }
            // 尾部落单的 1 字节直接丢弃
            return out;
        }

        // 其他 charset：走 iconv
        iconv_t cd = iconv_open("UTF-8", charset.c_str());
        if (cd == reinterpret_cast<iconv_t>(-1)) {
            return std::string();
        }

            char outbuf[4096];
        std::size_t inLeft = src.size();
        const char* inPtr = src.data();

        while (inLeft > 0) {
            char* inTmp = const_cast<char*>(inPtr);
            std::size_t inAvail = inLeft;
            char* outTmp = outbuf;
            std::size_t outAvail = sizeof(outbuf);

            const std::size_t rc = iconv(cd, &inTmp, &inAvail, &outTmp, &outAvail);
            const std::size_t produced = sizeof(outbuf) - outAvail;
            if (produced > 0) {
                out.append(outbuf, produced);
            }

            if (rc != static_cast<std::size_t>(-1)) {
                inPtr = inTmp;
                inLeft = inAvail;
                continue;
            }

            if (errno == E2BIG) {
                // 输出缓冲用满：已产出追加到结果串并继续
                inPtr = inTmp;
                inLeft = inAvail;
                continue;
            } else if (errno == EILSEQ) {
                // 非法序列：替换为 U+FFFD 并跳过 1 个输入字节
                appendUtf8(out, 0xFFFD);
                if (inAvail > 0) {
                    inTmp += 1;
                    inAvail -= 1;
                }
                inPtr = inTmp;
                inLeft = inAvail;
                continue;
            } else if (errno == EINVAL) {
                // 不完整序列：截断结束
                break;
            } else {
                iconv_close(cd);
                return std::string();
            }
        }

        iconv_close(cd);
        return out;
    } catch (...) {
        return std::string();
    }
}

HtmlExtractResult HtmlExtractor::extractFromBytes(const std::string& rawBytes) noexcept {
    // 探测 + 解码 + 提取一站式，永不抛异常
    HtmlExtractResult res;
    try {
        if (rawBytes.empty()) {
            res.ok = true;
            res.usedCharset = "UTF-8";
            return res;
        }
        std::string cs = detectCharset(rawBytes);
        res.usedCharset = cs;
        std::string utf8 = decodeToUtf8(rawBytes, cs);
        if (utf8.empty()) {
            res.ok = false;
            return res;
        }
        res.doc = extract(utf8);
        res.ok = true;
    } catch (...) {
        res.ok = false;
    }
    return res;
}

HtmlExtracted HtmlExtractor::extract(const std::string& html) {
HtmlExtracted result;
bool inTitle = false;

RawBuilder body;
RawBuilder titleBuilder;

size_t i = 0;
const size_t n = html.size();

auto skipToEnd = [&](const std::string& closeTag) -> bool {
// 大小写不敏感查找 closeTag，返回是否找到
size_t j = i;
const size_t clen = closeTag.size();
while (j + clen <= n) {
bool match = true;
for (size_t k = 0; k < clen; ++k) {
if (toLowerAscii(html[j + k]) != closeTag[k]) { match = false; break; }
}
if (match) {
i = j + clen;
return true;
}
++j;
}
i = n;
return false;
};

while (i < n) {
char c = html[i];
if (c == '<') {
// 注释
if (i + 3 < n && html[i + 1] == '!' && html[i + 2] == '-' && html[i + 3] == '-') {
i += 4;
skipToEnd("-->");
continue;
}
// DOCTYPE 或 <!...>
if (i + 1 < n && html[i + 1] == '!') {
i += 2;
while (i < n && html[i] != '>') ++i;
if (i < n) ++i;
continue;
}
// 处理指令 <? ... ?>
if (i + 1 < n && html[i + 1] == '?') {
i += 2;
while (i < n && html[i] != '>') ++i;
if (i < n) ++i;
continue;
}
// 结束标签
if (i + 1 < n && html[i + 1] == '/') {
size_t p = i + 2;
size_t ns = p;
while (p < n && isNameChar(html[p])) ++p;
std::string name = toLower(html.substr(ns, p - ns));
while (p < n && html[p] != '>') ++p;
if (p < n) ++p;
i = p;
if (name == "title") {
inTitle = false;
}
if (isBlockTag(name)) {
body.addNewline();
}
continue;
}
// 开始标签
size_t p = i + 1;
size_t ns = p;
while (p < n && isNameChar(html[p])) ++p;
std::string name = toLower(html.substr(ns, p - ns));
if (name.empty()) {
// 不是合法标签，当普通字符处理
body.addChar('<');
++i;
continue;
}
// 收集属性
bool selfClosing = false;
std::string attrName;
std::string attrValue;
bool hasAttr = false;
std::vector<std::pair<std::string, std::string>> attrs;
while (p < n) {
while (p < n && isSpaceChar(html[p])) ++p;
if (p >= n) break;
if (html[p] == '>') { ++p; break; }
if (html[p] == '/') {
if (p + 1 < n && html[p + 1] == '>') { selfClosing = true; p += 2; break; }
++p;
continue;
}
size_t ans = p;
while (p < n && isNameChar(html[p])) ++p;
if (p == ans) { ++p; continue; }
attrName = toLower(html.substr(ans, p - ans));
attrValue.clear();
hasAttr = false;
while (p < n && isSpaceChar(html[p])) ++p;
if (p < n && html[p] == '=') {
++p;
while (p < n && isSpaceChar(html[p])) ++p;
if (p < n && (html[p] == '"' || html[p] == '\'')) {
char q = html[p];
++p;
size_t vs = p;
while (p < n && html[p] != q) ++p;
attrValue = html.substr(vs, p - vs);
if (p < n) ++p;
} else {
size_t vs = p;
while (p < n && !isSpaceChar(html[p]) && html[p] != '>') ++p;
attrValue = html.substr(vs, p - vs);
}
hasAttr = true;
}
attrs.emplace_back(attrName, hasAttr ? attrValue : std::string());
}
i = p;

// script/style/noscript 剔除
if (name == "script" || name == "style" || name == "noscript") {
if (!selfClosing) {
std::string close = "</" + name;
skipToEnd(close);
// skipToEnd 停在闭合标签的 '>' 上（或输入结尾），把 '>' 一并吞掉，避免泄漏为正文
while (i < n && isSpaceChar(html[i])) ++i;
if (i < n && html[i] == '>') ++i;
}
continue;
}

// title
if (name == "title" && !selfClosing) {
inTitle = true;
continue;
}

// meta description
if (name == "meta") {
std::string mname;
std::string mcontent;
for (const auto& kv : attrs) {
if (kv.first == "name") mname = toLower(kv.second);
else if (kv.first == "content") mcontent = kv.second;
}
if (mname == "description" && result.description.empty()) {
result.description = mcontent;
}
continue;
}

if (isBlockTag(name)) {
body.addNewline();
}
continue;
}

// 普通字符
if (c == '&') {
size_t consumed = 0;
std::string decoded;
if (decodeEntity(html, i + 1, consumed, decoded)) {
if (inTitle) {
for (char dc : decoded) titleBuilder.addChar(dc);
} else {
body.addString(decoded);
}
i += 1 + consumed;
continue;
}
if (inTitle) titleBuilder.addChar('&');
else body.addChar('&');
++i;
continue;
}

if (inTitle) {
titleBuilder.addChar(c);
} else {
body.addChar(c);
}
++i;
}

result.title = titleBuilder.finalize();
result.text = body.finalize();
return result;
}

} // namespace docseek
