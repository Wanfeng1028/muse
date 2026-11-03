#pragma once

#include <string>

namespace docseek {

// HTML 文本提取结果
struct HtmlExtracted {
    std::string title;        // <title> 文本（无则为空）
    std::string description;  // <meta name="description"> 的 content（无则为空）
    std::string text;         // 去标签后的正文文本
};

// 带编码信息与成功标志的提取结果
struct HtmlExtractResult {
    bool ok = false;               // 提取是否成功
    HtmlExtracted doc;             // 提取出的内容
    std::string usedCharset;       // 实际使用的字符集名称
};

// HTML 文本提取器：零第三方依赖，纯字符串扫描
class HtmlExtractor {
public:
    // 从 HTML 源码提取标题、meta description 与正文。
    // 输入应为 UTF-8 编码。
    static HtmlExtracted extract(const std::string& html);

    // 编码探测：BOM(UTF-8/UTF-16LE/BE) → <meta charset>/<meta http-equiv>
    // → 默认 "UTF-8"。返回规范化的大写名称，如 "UTF-8"、"UTF-16LE"、
    // "UTF-16BE"，或 meta 中声明的原样名称（大写化）。
    static std::string detectCharset(const std::string& rawBytes);

    // 按 charset 将原始字节转换为 UTF-8。
    // 失败返回空串；空输入返回空串。
    // UTF-16LE/BE 手写转换；其余（UTF-8 / GB18030 / BIG5 / WINDOWS-1252 等）
    // 走系统 iconv。
    static std::string decodeToUtf8(const std::string& rawBytes,
                                    const std::string& charset);

    // 探测 + 解码 + extract 一站式，永不抛异常。
    // 空输入视为成功（doc 全空，usedCharset="UTF-8"）。
    static HtmlExtractResult extractFromBytes(const std::string& rawBytes) noexcept;
};

}  // namespace docseek
