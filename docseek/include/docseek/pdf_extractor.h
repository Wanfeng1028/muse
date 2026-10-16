#pragma once

#include <string>

namespace docseek {

// PDF 文本提取结果
struct PdfExtractResult {
    bool ok = false;          // 提取是否成功
    std::string text;         // UTF-8 全文，页间以 '\f' 分隔
    int pages = 0;            // 成功时的页数（按 '\f' 个数计；无 '\f' 但文本非空时为 1）
    bool encrypted = false;   // 是否识别为加密 PDF（此时 ok=false）
    std::string error;        // ok=false 且非加密时的错误说明
};

// PDF 文本提取器：子进程调用系统 pdftotext，零构建依赖
class PdfExtractor {
public:
    // 从文件路径提取全文（所有页）
    static PdfExtractResult extractFromPath(const std::string& path) noexcept;

    // 提取第 firstPage..lastPage 页（1-based 闭区间，越界自动钳制）
    static PdfExtractResult extractPages(const std::string& path, int firstPage, int lastPage) noexcept;

    // 系统 pdftotext 是否可用
    static bool isAvailable() noexcept;

    // 覆盖 pdftotext 二进制路径（空串恢复默认 "pdftotext"），仅测试用
    static void setBinaryPathForTest(const std::string& p);
};

}  // namespace docseek
