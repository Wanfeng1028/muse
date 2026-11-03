#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace docseek {

// Office 文档文本提取结果
struct OfficeExtractResult {
  bool ok = false;      // 提取是否成功
  std::string text;     // UTF-8 全文
  std::string error;    // ok=false 时的错误说明
};

// 只读 ZIP 解析器（纯自研，无第三方依赖）。
//
// license 路由选择理由：自研 zip 解析 + 系统 zlib（zlib license，宽松许可），
// 延续项目"零 GPL 污染"原则（参见 docs/PDF_EXTRACTION_SELECTION.md）。
//
// 支持：stored(0) 与 deflated(8) 两种压缩方法。
// 不支持：data descriptor（bit 3 置位）与加密条目，遇到时给出诚实 error。
// 安全上限（防 zip bomb）：
//   - 条目数 <= 100000
//   - central directory 总大小 <= 256MB
//   - 单个条目解压后大小 <= 512MB
class ZipReader {
public:
  ZipReader() noexcept = default;
  ~ZipReader() noexcept = default;
  ZipReader(const ZipReader&) = delete;
  ZipReader& operator=(const ZipReader&) = delete;
  ZipReader(ZipReader&&) noexcept = default;
  ZipReader& operator=(ZipReader&&) noexcept = default;

  // 打开 zip 文件：读 EOCD → 解析 central directory → 建立条目表。
  // 任一安全上限超限或格式损坏时返回 false 并给出 error。
  bool open(const std::string& path, std::string& error) noexcept;

  // 是否存在指定名字的条目
  bool hasEntry(const std::string& name) const noexcept;

  // 读取指定条目内容到 out。stored 直接拷贝，deflated 经 zlib inflate 解压。
  // 解压后大小与 central directory 记录的 uncompressed size 不一致则返回 false。
  bool readEntry(const std::string& name, std::string& out,
                 std::string& error) const noexcept;

  // 全部条目名（按 central directory 出现顺序）
  std::vector<std::string> entryNames() const;

private:
  struct Entry {
    std::string name;
    uint16_t method = 0;              // 0=stored, 8=deflated
    uint16_t flags = 0;               // 通用位标记
    uint32_t compressedSize = 0;
    uint32_t uncompressedSize = 0;
    uint64_t localHeaderOffset = 0;   // local file header 相对文件起点的偏移
  };

  std::string path_;                  // zip 文件路径
  uint64_t fileSize_ = 0;             // 文件总大小
  std::vector<Entry> entries_;        // 条目表

  // 读取整个文件到内存（内部使用；调用前应先做大小上限检查）
  bool readWholeFile(std::string& out, std::string& error) const noexcept;
};

// DOCX 文本提取器：ZipReader 读取 word/document.xml，手写扫描 <w:t>。
class DocxExtractor {
public:
  static OfficeExtractResult extractFromPath(const std::string& path) noexcept;
};

// XLSX 提取器
class XlsxExtractor {
public:
  struct SheetText {
    std::string sheetName;
    std::string text;
  };
  struct XlsxResult {
    bool ok = false;
    std::vector<SheetText> sheets;
    std::string error;
  };
  static XlsxResult extractFromPath(const std::string& path) noexcept;
};

// PPTX 提取器
class PptxExtractor {
public:
  struct SlideText {
    int slideNo = 0;
    std::string text;
  };
  struct PptxResult {
    bool ok = false;
    std::vector<SlideText> slides;
    std::string error;
  };
  static PptxResult extractFromPath(const std::string& path) noexcept;
};

}  // namespace docseek
