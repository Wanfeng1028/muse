#include "docseek/structural_precision.h"

#include <cstddef>
#include <string>
#include <vector>

namespace docseek {
namespace {

// 返回 s[i] 处 UTF-8 字符占用的字节数：
// 0x00-0x7F 返回 1；0xC0-0xDF 返回 2；0xE0-0xEF 返回 3；0xF0-0xF7 返回 4；其他返回 1。
// 注意：调用方保证 i < s.size()。
size_t utf8CharLen(unsigned char c) {
    if (c <= 0x7F) {
        return 1;
    }
    if (c >= 0xC0 && c <= 0xDF) {
        return 2;
    }
    if (c >= 0xE0 && c <= 0xEF) {
        return 3;
    }
    if (c >= 0xF0 && c <= 0xF7) {
        return 4;
    }
    return 1;
}

// 返回 s 的 UTF-8 码点总数。非法字节按 1 字节推进，保证不死循环。
size_t countCodepoints(const std::string& s) {
    size_t n = 0;
    size_t i = 0;
    while (i < s.size()) {
        i += utf8CharLen(static_cast<unsigned char>(s[i]));
        ++n;
    }
    return n;
}


// 判断 s 从字节下标 pos 处开始是否为一个数字字符。
// 是则返回 true，并把该字符的字节数写入 outLen；否则返回 false，outLen 不变。
bool isDigitCharAt(const std::string& s, size_t pos, size_t& outLen)
{
    // 防御：下标越界。
    if (pos >= s.size()) {
        return false;
    }

    unsigned char c = static_cast<unsigned char>(s[pos]);

    // ASCII 数字 '0'-'9'，占 1 字节。
    if (c >= '0' && c <= '9') {
        outLen = 1;
        return true;
    }

    // 可能是 UTF-8 多字节字符。
    if (c >= 0x80) {
        size_t len = utf8CharLen(c); // 中文数字通常为 3 字节。

        if (len != 0 && pos <= s.size() && len <= s.size() - pos) {
            static const std::string cnDigits = "一二三四五六七八九十百千万两";
            std::string ch = s.substr(pos, len);

            if (cnDigits.find(ch) != std::string::npos) {
                outLen = len;
                return true;
            }
        }
    }

    return false;
}

}  // namespace

bool isEntryLikeLineStart(const std::string& strippedLine, bool hadListMarker,
                          size_t queryByteLen) {
    // (a) 如果该行原本带有列表符号，则直接视为条目起始行。
    if (hadListMarker) {
        return true;
    }

    // (b) 如果整行码点数不超过 40，也视为条目起始行。
    if (countCodepoints(strippedLine) <= 40) {
        return true;
    }

    // (c) 查询词之后的连续 3 个 UTF-8 字符中出现冒号或破折号。
    // 若 queryByteLen 越界，或没有查询词后内容，则跳过。
    if (queryByteLen >= strippedLine.size()) {
        return false;
    }

    size_t pos = queryByteLen;
    for (int i = 0; i < 3; ++i) {
        if (pos >= strippedLine.size()) {
            break;
        }

        unsigned char c = static_cast<unsigned char>(strippedLine[pos]);
        size_t charLen = utf8CharLen(c);

        // UTF-8 标点判断。
        if (c == ':' || c == '-') {
            return true;
        }

        if (charLen == 3 && pos + 2 < strippedLine.size()) {
            unsigned char b1 = static_cast<unsigned char>(strippedLine[pos + 1]);
            unsigned char b2 = static_cast<unsigned char>(strippedLine[pos + 2]);

            // "：" 的 UTF-8 编码是 E8 A1 9A。
            if (c == 0xE8 && b1 == 0xA1 && b2 == 0x9A) {
                return true;
            }
        }

        if (charLen == 3 && pos + 2 < strippedLine.size()) {
            unsigned char b1 = static_cast<unsigned char>(strippedLine[pos + 1]);
            unsigned char b2 = static_cast<unsigned char>(strippedLine[pos + 2]);

            // "–" 的 UTF-8 编码是 E2 80 93。
            if (c == 0xE2 && b1 == 0x80 && b2 == 0x93) {
                return true;
            }

            // "—" 的 UTF-8 编码是 E2 80 94。
            if (c == 0xE2 && b1 == 0x80 && b2 == 0x94) {
                return true;
            }
        }

        pos += charLen;
    }

    return false;
}

bool digitConsistentWithQuery(const std::string& strippedLine,
                              const std::string& query) {
    // 步骤1：若 query 自身含有数字字符，
    // 由于 strippedLine 保证以 query 开头，行首数字已属于查询词的一部分，
    // 数字一致性恒成立，直接返回 true。
    size_t qpos = 0;
    while (qpos < query.size()) {
        size_t digitLen = 0;
        if (isDigitCharAt(query, qpos, digitLen)) {
            return true;
        }

        size_t advance = utf8CharLen(static_cast<unsigned char>(query[qpos]));
        if (advance == 0) {
            advance = 1;
        }
        qpos += advance;
    }

    // 步骤3：防御性处理，避免 query.size() 越界。
    size_t pos = query.size();
    if (pos > strippedLine.size()) {
        pos = strippedLine.size();
    }

    // 步骤2：query 无数字时，只把“查询结尾后较近位置”的数字视为事物计数。
    // dist 从 0 开始，表示 query 结尾后的第几个码点；
    // 第一个数字必须落在 dist <= 10 的范围内。
    size_t dist = 0;
    while (pos < strippedLine.size()) {
        size_t digitLen = 0;
        if (isDigitCharAt(strippedLine, pos, digitLen)) {
            return dist <= 10;
        }

        size_t advance = utf8CharLen(static_cast<unsigned char>(strippedLine[pos]));
        if (advance == 0) {
            advance = 1;
        }
        pos += advance;
        ++dist;
    }

    return false;
}

double r1StartsWithBonusForToken(const std::vector<std::string>& headings,
                                 const std::string& token)
{
    // a) token 为空时无意义，直接返回 0.0。
    if (token.empty()) {
        return 0.0;
    }

    const auto tokenLen = token.size();
    const auto tokenCodepoints = countCodepoints(token);

    bool hasPrefixLonger = false;
    bool hasSubstring = false;

    for (const auto& h : headings) {
        // b) 强对应：标题以 token 开头，且标题码点数不超出查询词 2 个码点。
        if (h.size() >= tokenLen && h.compare(0, tokenLen, token) == 0) {
            if (countCodepoints(h) <= tokenCodepoints + 2) {
                return 1.5;
            }
            // b1) 中间档：标题以 token 开头，但标题码点数超出查询词 2 个码点。
            hasPrefixLonger = true;
        }

        // c) 记录是否存在包含 token 的标题；即使是以 token 开头但超长，也属于包含。
        if (h.find(token) != std::string::npos) {
            hasSubstring = true;
        }
    }

    // b1 未命中则按 c 降级处理。
    return hasPrefixLonger ? 0.75 : (hasSubstring ? 0.25 : 0.0);
}

}  // namespace docseek
