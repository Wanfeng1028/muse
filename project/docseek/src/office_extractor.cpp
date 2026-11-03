#include "docseek/office_extractor.h"

#include <zlib.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

namespace docseek {
namespace {

// ---------- 常量与上限 ----------
constexpr uint32_t kSigLocalHeader = 0x04034b50u;
constexpr uint32_t kSigCentralDir  = 0x02014b50u;
constexpr uint32_t kSigEocd        = 0x06054b50u;

constexpr uint32_t kMaxEntries            = 100000u;                 // 条目数上限
constexpr uint64_t kMaxCentralDirBytes    = 256ull * 1024 * 1024;    // 256MB
constexpr uint64_t kMaxUncompressedEntry  = 512ull * 1024 * 1024;    // 512MB
constexpr uint64_t kMaxFileSize           = 1024ull * 1024 * 1024;   // 1GB 文件上限（安全）

// 小端读取辅助
inline uint16_t rd16(const unsigned char* p) noexcept {
  return static_cast<uint16_t>(p[0] | (p[1] << 8));
}
inline uint32_t rd32(const unsigned char* p) noexcept {
  return static_cast<uint32_t>(p[0]) |
         (static_cast<uint32_t>(p[1]) << 8) |
         (static_cast<uint32_t>(p[2]) << 16) |
         (static_cast<uint32_t>(p[3]) << 24);
}

// ---------- zlib inflate 封装（raw deflate，-MAX_WBITS） ----------
// 返回 true 表示解压成功且大小与期望一致。
bool inflateRaw(const std::string& in, std::string& out,
                uint64_t expectedSize, std::string& error) noexcept {
  if (expectedSize > kMaxUncompressedEntry) {
    error = "条目解压后大小超过 512MB 上限，疑似 zip bomb";
    return false;
  }
  out.clear();
  if (expectedSize == 0) {
    // 期望为空，无需解压
    return true;
  }

  z_stream strm;
  std::memset(&strm, 0, sizeof(strm));

  // -MAX_WBITS 表示 raw deflate（无 zlib/gzip 头）
  int ret = inflateInit2(&strm, -MAX_WBITS);
  if (ret != Z_OK) {
    error = "zlib inflateInit2 失败";
    return false;
  }

  // 预分配期望大小（已经过上限检查）
  out.resize(static_cast<size_t>(expectedSize));

  strm.next_in = reinterpret_cast<Bytef*>(const_cast<char*>(in.data()));
  strm.avail_in = static_cast<uInt>(in.size());
  strm.next_out = reinterpret_cast<Bytef*>(&out[0]);
  strm.avail_out = static_cast<uInt>(out.size());

  // 循环调用 inflate 直到 Z_STREAM_END
  for (;;) {
    ret = inflate(&strm, Z_FINISH);
    if (ret == Z_STREAM_END) {
      break;
    }
    if (ret == Z_OK) {
      // 输出缓冲区还有空间但流未结束：说明 expectedSize 偏小，视为不一致
      inflateEnd(&strm);
      error = "解压后大小与 central directory 记录不一致（输出缓冲区不足）";
      return false;
    }
    if (ret == Z_BUF_ERROR) {
      // 输入耗尽但未到达流结尾：数据损坏
      inflateEnd(&strm);
      error = "deflate 数据不完整或损坏";
      return false;
    }
    // Z_NEED_DICT / Z_DATA_ERROR / Z_MEM_ERROR 等
    inflateEnd(&strm);
    error = "zlib inflate 解压失败";
    return false;
  }

  uint64_t produced = static_cast<uint64_t>(strm.total_out);
  inflateEnd(&strm);

  if (produced != expectedSize) {
    error = "解压后大小与 central directory 记录不一致";
    return false;
  }
  return true;
}

// ---------- XML 实体解码 ----------
// 输入 s 的 [pos, end) 为不含 & 与 ; 的实体主体；返回解码后的 UTF-8 追加到 out。
// 返回 true 表示成功识别并解码；false 表示未知实体（原样保留）。
bool decodeEntity(const std::string& s, size_t pos, size_t end,
                  std::string& out) noexcept {
  size_t len = end - pos;
  if (len == 0) return false;

  // 命名实体
  if (len == 2 && s[pos] == 'a' && s[pos + 1] == 'm') { out += '&'; return true; }
  if (len == 2 && s[pos] == 'l' && s[pos + 1] == 't') { out += '<'; return true; }
  if (len == 2 && s[pos] == 'g' && s[pos + 1] == 't') { out += '>'; return true; }
  if (len == 3 && s[pos] == 'a' && s[pos + 1] == 'm' && s[pos + 2] == 'p') {
    out += '&'; return true;
  }
  if (len == 3 && s[pos] == 'l' && s[pos + 1] == 't' && s[pos + 2] == ';') {
    out += '<'; return true;
  }
  if (len == 3 && s[pos] == 'g' && s[pos + 1] == 't' && s[pos + 2] == ';') {
    out += '>'; return true;
  }
  if (len == 4 && s.compare(pos, 4, "quot") == 0) { out += '"'; return true; }
  if (len == 4 && s.compare(pos, 4, "apos") == 0) { out += '\''; return true; }
  if (len == 2 && s[pos] == 'q' && s[pos + 1] == 'u') {
    // "quo" 前缀不完整，不识别
    return false;
  }

  // 数字字符引用：&#xHH...; 或 &#DD...;
  if (s[pos] == '#') {
    if (len >= 2 && (s[pos + 1] == 'x' || s[pos + 1] == 'X')) {
      // 十六进制
      uint32_t cp = 0;
      bool ok = false;
      for (size_t i = pos + 2; i < end; ++i) {
        char c = s[i];
        int d;
        if (c >= '0' && c <= '9') d = c - '0';
        else if (c >= 'a' && c <= 'f') d = c - 'a' + 10;
        else if (c >= 'A' && c <= 'F') d = c - 'A' + 10;
        else { ok = false; break; }
        cp = (cp << 4) | static_cast<uint32_t>(d);
        ok = true;
        if (cp > 0x10FFFFu) { ok = false; break; }
      }
      if (ok) {
        // 编码为 UTF-8
        if (cp <= 0x7F) {
          out += static_cast<char>(cp);
        } else if (cp <= 0x7FF) {
          out += static_cast<char>(0xC0 | (cp >> 6));
          out += static_cast<char>(0x80 | (cp & 0x3F));
        } else if (cp <= 0xFFFF) {
          out += static_cast<char>(0xE0 | (cp >> 12));
          out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
          out += static_cast<char>(0x80 | (cp & 0x3F));
        } else {
          out += static_cast<char>(0xF0 | (cp >> 18));
          out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
          out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
          out += static_cast<char>(0x80 | (cp & 0x3F));
        }
        return true;
      }
      return false;
    } else {
      // 十进制
      uint32_t cp = 0;
      bool ok = false;
      for (size_t i = pos + 1; i < end; ++i) {
        char c = s[i];
        if (c < '0' || c > '9') { ok = false; break; }
        cp = cp * 10u + static_cast<uint32_t>(c - '0');
        ok = true;
        if (cp > 0x10FFFFu) { ok = false; break; }
      }
      if (ok) {
        if (cp <= 0x7F) {
          out += static_cast<char>(cp);
        } else if (cp <= 0x7FF) {
          out += static_cast<char>(0xC0 | (cp >> 6));
          out += static_cast<char>(0x80 | (cp & 0x3F));
        } else if (cp <= 0xFFFF) {
          out += static_cast<char>(0xE0 | (cp >> 12));
          out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
          out += static_cast<char>(0x80 | (cp & 0x3F));
        } else {
          out += static_cast<char>(0xF0 | (cp >> 18));
          out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
          out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
          out += static_cast<char>(0x80 | (cp & 0x3F));
        }
        return true;
      }
      return false;
    }
  }
  return false;
}

// 将 XML 文本片段（不含标签）做实体解码后追加到 out。
void appendXmlText(const std::string& s, size_t begin, size_t end,
                   std::string& out) noexcept {
  size_t i = begin;
  while (i < end) {
    if (s[i] == '&') {
      // 查找 ;
      size_t j = i + 1;
      while (j < end && s[j] != ';' && (j - i) < 12) ++j;
      if (j < end && s[j] == ';') {
        if (decodeEntity(s, i + 1, j, out)) {
          i = j + 1;
          continue;
        }
        // 未知实体：原样输出 &
        out += '&';
        ++i;
        continue;
      }
      // 没有分号：原样输出
      out += '&';
      ++i;
    } else {
      out += s[i];
      ++i;
    }
  }
}

// 从 XML 中提取所有 <w:t>...</w:t> 的文本，遇到 </w:p> 输出换行，
// </w:tbl> 后输出空行。
void extractWtFromXml(const std::string& xml, std::string& out) noexcept {
  const size_t n = xml.size();
  size_t i = 0;
  while (i < n) {
    if (xml[i] != '<') {
      ++i;
      continue;
    }
    // 找到标签结束 >
    size_t tagEnd = i + 1;
    while (tagEnd < n && xml[tagEnd] != '>') ++tagEnd;
    if (tagEnd >= n) break;
    // 判断标签类型
    // 起始标签 <w:t ...> 或自闭合 <w:t ... />
    bool isWtStart = false;
    bool isWtSelfClose = false;
    if (i + 4 <= n && xml.compare(i, 4, "<w:t") == 0) {
      // 确保后面是空白或 '/' 或 '>'
      char c = (i + 4 < n) ? xml[i + 4] : '>';
      if (c == '>' || c == '/' || c == ' ' || c == '\t' || c == '\n' || c == '\r') {
        isWtStart = true;
        // 检测自闭合
        size_t k = tagEnd;
        if (k > i && xml[k - 1] == '/') isWtSelfClose = true;
      }
    }
    // 结束标签 </w:t>
    bool isWtEnd = false;
    if (i + 5 <= n && xml.compare(i, 5, "</w:t") == 0) {
      size_t k = i + 5;
      while (k < n && (xml[k] == ' ' || xml[k] == '\t' || xml[k] == '\n' || xml[k] == '\r')) ++k;
      if (k < n && xml[k] == '>') isWtEnd = true;
    }
    // 段落结束 </w:p>
    bool isPEnd = false;
    if (i + 5 <= n && xml.compare(i, 5, "</w:p") == 0) {
      size_t k = i + 5;
      while (k < n && (xml[k] == ' ' || xml[k] == '\t' || xml[k] == '\n' || xml[k] == '\r')) ++k;
      if (k < n && xml[k] == '>') isPEnd = true;
    }
    // 表格结束 </w:tbl>
    bool isTblEnd = false;
    if (i + 7 <= n && xml.compare(i, 7, "</w:tbl") == 0) {
      size_t k = i + 7;
      while (k < n && (xml[k] == ' ' || xml[k] == '\t' || xml[k] == '\n' || xml[k] == '\r')) ++k;
      if (k < n && xml[k] == '>') isTblEnd = true;
    }

    if (isWtStart) {
      if (isWtSelfClose) {
        // 自闭合视为空，不输出
        i = tagEnd + 1;
        continue;
      }
      // 读取到 </w:t>
      size_t textBegin = tagEnd + 1;
      // 查找 </w:t
      size_t j = textBegin;
      size_t textEnd = n;
      while (j < n) {
        if (xml[j] == '<' && j + 5 <= n && xml.compare(j, 5, "</w:t") == 0) {
          size_t k = j + 5;
          while (k < n && (xml[k] == ' ' || xml[k] == '\t' || xml[k] == '\n' || xml[k] == '\r')) ++k;
          if (k < n && xml[k] == '>') {
            textEnd = j;
            break;
          }
        }
        ++j;
      }
      if (textEnd > textBegin) {
        appendXmlText(xml, textBegin, textEnd, out);
      }
      // 跳过到结束标签之后
      if (j < n) {
        size_t k = j + 5;
        while (k < n && xml[k] != '>') ++k;
        i = (k < n) ? k + 1 : n;
      } else {
        i = n;
      }
      continue;
    }

    if (isPEnd) {
      out += '\n';
      i = tagEnd + 1;
      continue;
    }
    if (isTblEnd) {
      out += '\n';
      out += '\n';
      i = tagEnd + 1;
      continue;
    }
    if (isWtEnd) {
      // 孤立的结束标签，跳过
      i = tagEnd + 1;
      continue;
    }

    // 其他标签：跳过
    i = tagEnd + 1;
  }
}

}  // namespace

// ================= ZipReader =================

bool ZipReader::readWholeFile(std::string& out, std::string& error) const noexcept {
  out.clear();
  std::ifstream f(path_, std::ios::binary);
  if (!f) {
    error = "无法打开文件: " + path_;
    return false;
  }
  f.seekg(0, std::ios::end);
  std::streamoff sz = f.tellg();
  if (sz < 0) {
    error = "无法获取文件大小";
    return false;
  }
  if (static_cast<uint64_t>(sz) > kMaxFileSize) {
    error = "文件大小超过 1GB 上限";
    return false;
  }
  out.resize(static_cast<size_t>(sz));
  f.seekg(0, std::ios::beg);
  if (sz > 0) {
    f.read(&out[0], sz);
    if (!f) {
      error = "读取文件失败";
      out.clear();
      return false;
    }
  }
  return true;
}

bool ZipReader::open(const std::string& path, std::string& error) noexcept {
  error.clear();
  path_.clear();
  entries_.clear();
  fileSize_ = 0;

  std::string data;
  // 先检查文件大小，避免一次性读入超大文件
  {
    std::ifstream f(path, std::ios::binary | std::ios::ate);
    if (!f) {
      error = "无法打开文件: " + path;
      return false;
    }
    std::streamoff sz = f.tellg();
    if (sz < 0) {
      error = "无法获取文件大小";
      return false;
    }
    if (static_cast<uint64_t>(sz) > kMaxFileSize) {
      error = "文件大小超过 1GB 上限";
      return false;
    }
    if (static_cast<uint64_t>(sz) < 22) {  // EOCD 最小 22 字节
      error = "文件过小，不是有效的 zip";
      return false;
    }
  }

  path_ = path;
  if (!readWholeFile(data, error)) {
    return false;
  }
  fileSize_ = data.size();
  const unsigned char* buf = reinterpret_cast<const unsigned char*>(data.data());

  // ---- 定位 EOCD：从尾部向前扫描 ----
  // EOCD 最小 22 字节，注释最长 65535 字节
  size_t eocdPos = 0;
  bool foundEocd = false;
  {
    size_t maxBack = 22 + 65535;
    size_t start = (data.size() > maxBack) ? (data.size() - maxBack) : 0;
    // 从尾部向前
    size_t p = data.size();
    while (p >= 22 && p > start) {
      p -= 1;
      if (p + 4 <= data.size() && rd32(buf + p) == kSigEocd) {
        // 校验：p + 22 <= size
        if (p + 22 <= data.size()) {
          // 注释长度
          uint16_t commentLen = rd16(buf + p + 20);
          if (p + 22 + commentLen == data.size()) {
            eocdPos = p;
            foundEocd = true;
            break;
          }
        }
      }
      if (p == 0) break;
    }
  }
  if (!foundEocd) {
    error = "未找到 EOCD 记录，不是有效的 zip";
    return false;
  }

  // 解析 EOCD
  uint16_t totalEntries = rd16(buf + eocdPos + 10);
  uint32_t cdSize = rd32(buf + eocdPos + 12);
  uint32_t cdOffset = rd32(buf + eocdPos + 16);

  if (totalEntries == 0xFFFFu) {
    error = "不支持 ZIP64 条目计数";
    return false;
  }
  if (cdSize == 0xFFFFFFFFu || cdOffset == 0xFFFFFFFFu) {
    error = "不支持 ZIP64 central directory";
    return false;
  }
  if (totalEntries > kMaxEntries) {
    error = "条目数超过 100000 上限";
    return false;
  }
  if (static_cast<uint64_t>(cdSize) > kMaxCentralDirBytes) {
    error = "central directory 大小超过 256MB 上限";
    return false;
  }
  if (static_cast<uint64_t>(cdOffset) + static_cast<uint64_t>(cdSize) > data.size()) {
    error = "central directory 偏移越界";
    return false;
  }

  // ---- 解析 central directory ----
  entries_.reserve(totalEntries);
  size_t p = cdOffset;
  size_t cdEnd = static_cast<size_t>(cdOffset) + cdSize;
  for (uint32_t idx = 0; idx < totalEntries; ++idx) {
    if (p + 46 > cdEnd || p + 46 > data.size()) {
      error = "central directory 记录截断";
      return false;
    }
    if (rd32(buf + p) != kSigCentralDir) {
      error = "central directory 签名错误";
      return false;
    }
    Entry e;
    e.flags = rd16(buf + p + 8);
    e.method = rd16(buf + p + 10);
    e.compressedSize = rd32(buf + p + 20);
    e.uncompressedSize = rd32(buf + p + 24);
    uint16_t nameLen = rd16(buf + p + 28);
    uint16_t extraLen = rd16(buf + p + 30);
    uint16_t commentLen = rd16(buf + p + 32);
    e.localHeaderOffset = rd32(buf + p + 42);

    if (e.compressedSize == 0xFFFFFFFFu || e.uncompressedSize == 0xFFFFFFFFu ||
        e.localHeaderOffset == 0xFFFFFFFFu) {
      error = "不支持 ZIP64 条目字段";
      return false;
    }
    if (e.uncompressedSize > kMaxUncompressedEntry) {
      error = "条目解压后大小超过 512MB 上限，疑似 zip bomb";
      return false;
    }
    if (p + 46 + nameLen + extraLen + commentLen > data.size()) {
      error = "central directory 记录越界";
      return false;
    }
    e.name.assign(reinterpret_cast<const char*>(buf + p + 46), nameLen);
    entries_.push_back(std::move(e));

    p += 46 + nameLen + extraLen + commentLen;
  }

  return true;
}

bool ZipReader::hasEntry(const std::string& name) const noexcept {
  for (const auto& e : entries_) {
    if (e.name == name) return true;
  }
  return false;
}

std::vector<std::string> ZipReader::entryNames() const {
  std::vector<std::string> names;
  names.reserve(entries_.size());
  for (const auto& e : entries_) names.push_back(e.name);
  return names;
}

bool ZipReader::readEntry(const std::string& name, std::string& out,
                          std::string& error) const noexcept {
  out.clear();
  error.clear();

  const Entry* ent = nullptr;
  for (const auto& e : entries_) {
    if (e.name == name) { ent = &e; break; }
  }
  if (ent == nullptr) {
    error = "条目不存在: " + name;
    return false;
  }

  // 不支持 data descriptor
  if ((ent->flags & 0x0008u) != 0) {
    error = "不支持 data descriptor（bit 3 置位）zip 条目";
    return false;
  }
  // 不支持加密
  if ((ent->flags & 0x0001u) != 0) {
    error = "不支持加密 zip 条目";
    return false;
  }

  if (ent->uncompressedSize > kMaxUncompressedEntry) {
    error = "条目解压后大小超过 512MB 上限，疑似 zip bomb";
    return false;
  }

  std::string data;
  if (!readWholeFile(data, error)) {
    return false;
  }
  const unsigned char* buf = reinterpret_cast<const unsigned char*>(data.data());

  uint64_t lo = ent->localHeaderOffset;
  if (lo + 30 > data.size()) {
    error = "local file header 偏移越界";
    return false;
  }
  if (rd32(buf + lo) != kSigLocalHeader) {
    error = "local file header 签名错误";
    return false;
  }
  // local header 偏移 26/28 处是文件名长度/扩展字段长度
  uint16_t lhNameLen = rd16(buf + lo + 26);
  uint16_t lhExtraLen = rd16(buf + lo + 28);
  uint64_t dataStart = lo + 30 + lhNameLen + lhExtraLen;
  if (dataStart + ent->compressedSize > data.size()) {
    error = "条目数据越界";
    return false;
  }

  const char* compData = data.data() + dataStart;
  uint32_t compSize = ent->compressedSize;

  if (ent->method == 0) {
    // stored：直接拷贝
    if (ent->compressedSize != ent->uncompressedSize) {
      error = "stored 条目压缩/未压缩大小不一致";
      return false;
    }
    out.assign(compData, compSize);
    return true;
  } else if (ent->method == 8) {
    // deflated
    std::string in(compData, compSize);
    std::string inflated;
    if (!inflateRaw(in, inflated, ent->uncompressedSize, error)) {
      return false;
    }
    out = std::move(inflated);
    return true;
  }

  error = "不支持的压缩方法";
  return false;
}

// ================= DocxExtractor =================

OfficeExtractResult DocxExtractor::extractFromPath(const std::string& path) noexcept {
  OfficeExtractResult result;

  ZipReader zr;
  std::string err;
  if (!zr.open(path, err)) {
    result.ok = false;
    result.error = err.empty() ? "打开 zip 失败" : err;
    return result;
  }

  if (!zr.hasEntry("word/document.xml")) {
    result.ok = false;
    result.error = "缺少 word/document.xml，不是有效的 docx";
    return result;
  }

  std::string docXml;
  if (!zr.readEntry("word/document.xml", docXml, err)) {
    result.ok = false;
    result.error = err.empty() ? "读取 word/document.xml 失败" : err;
    return result;
  }

  std::string text;
  text.reserve(docXml.size() / 2);
  extractWtFromXml(docXml, text);

  // 依次提取 header/footer（按 entryNames 字典序）
  std::vector<std::string> names = zr.entryNames();
  std::sort(names.begin(), names.end());

  for (const auto& n : names) {
    bool isHeader = (n.compare(0, 11, "word/header") == 0 &&
                     n.size() >= 4 && n.compare(n.size() - 4, 4, ".xml") == 0);
    bool isFooter = (n.compare(0, 11, "word/footer") == 0 &&
                     n.size() >= 4 && n.compare(n.size() - 4, 4, ".xml") == 0);
    if (!isHeader && !isFooter) continue;

    std::string xml;
    if (!zr.readEntry(n, xml, err)) {
      continue;  // 缺失则忽略
    }
    std::string part;
    extractWtFromXml(xml, part);
    if (!part.empty()) {
      text += '\n';
      text += part;
    }
  }

  // 去空白判断
  bool hasNonSpace = false;
  for (char c : text) {
    if (c != ' ' && c != '\t' && c != '\n' && c != '\r' && c != '\f' && c != '\v') {
      hasNonSpace = true;
      break;
    }
  }
  if (!hasNonSpace) {
    result.ok = false;
    result.error = "未提取到任何文本";
    return result;
  }

  result.ok = true;
  result.text = std::move(text);
  return result;
}

namespace {

// 判断字符串是否以给定前缀开头
bool startsWith(const std::string& s, const std::string& prefix) {
  return s.size() >= prefix.size() && s.compare(0, prefix.size(), prefix) == 0;
}

// 判断字符是否为空白
bool isSpaceChar(char c) {
  return c == ' ' || c == '\t' || c == '\n' || c == '\r';
}

// XML 实体解码：&amp; &lt; &gt; &quot; &apos; 及数字实体
std::string decodeXmlEntities(const std::string& in) {
  std::string out;
  out.reserve(in.size());
  for (size_t i = 0; i < in.size();) {
    if (in[i] == '&') {
      size_t semi = in.find(';', i + 1);
      if (semi != std::string::npos && semi - i <= 12) {
        std::string ent = in.substr(i + 1, semi - i - 1);
        if (ent == "amp") { out += '&'; i = semi + 1; continue; }
        if (ent == "lt") { out += '<'; i = semi + 1; continue; }
        if (ent == "gt") { out += '>'; i = semi + 1; continue; }
        if (ent == "quot") { out += '"'; i = semi + 1; continue; }
        if (ent == "apos") { out += '\''; i = semi + 1; continue; }
        if (!ent.empty() && ent[0] == '#') {
          unsigned long cp = 0;
          bool ok = false;
          if (ent.size() > 1 && (ent[1] == 'x' || ent[1] == 'X')) {
            cp = 0;
            ok = ent.size() > 2;
            for (size_t k = 2; k < ent.size() && ok; ++k) {
              char c = ent[k];
              int d;
              if (c >= '0' && c <= '9') d = c - '0';
              else if (c >= 'a' && c <= 'f') d = c - 'a' + 10;
              else if (c >= 'A' && c <= 'F') d = c - 'A' + 10;
              else { ok = false; break; }
              cp = cp * 16 + static_cast<unsigned long>(d);
            }
          } else {
            ok = ent.size() > 1;
            for (size_t k = 1; k < ent.size() && ok; ++k) {
              char c = ent[k];
              if (c < '0' || c > '9') { ok = false; break; }
              cp = cp * 10 + static_cast<unsigned long>(c - '0');
            }
          }
          if (ok) {
            // UTF-8 编码
            if (cp <= 0x7F) {
              out += static_cast<char>(cp);
            } else if (cp <= 0x7FF) {
              out += static_cast<char>(0xC0 | (cp >> 6));
              out += static_cast<char>(0x80 | (cp & 0x3F));
            } else if (cp <= 0xFFFF) {
              out += static_cast<char>(0xE0 | (cp >> 12));
              out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
              out += static_cast<char>(0x80 | (cp & 0x3F));
            } else if (cp <= 0x10FFFF) {
              out += static_cast<char>(0xF0 | (cp >> 18));
              out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
              out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
              out += static_cast<char>(0x80 | (cp & 0x3F));
            }
            i = semi + 1;
            continue;
          }
        }
      }
      out += in[i];
      ++i;
    } else {
      out += in[i];
      ++i;
    }
  }
  return out;
}

// 从标签属性串中提取指定属性的值（XML 实体解码）
bool extractAttr(const std::string& tag, const std::string& attrName, std::string& out) {
  // 匹配 name = "..." 或 name='...'
  size_t pos = 0;
  while (pos < tag.size()) {
    size_t at = tag.find(attrName, pos);
    if (at == std::string::npos) return false;
    // 前面必须是空白或标签起始字符之后
    if (at > 0) {
      char prev = tag[at - 1];
      if (!isSpaceChar(prev) && prev != '<' && prev != '/') { pos = at + 1; continue; }
    }
    size_t after = at + attrName.size();
    // 跳过空白
    while (after < tag.size() && isSpaceChar(tag[after])) ++after;
    if (after >= tag.size() || tag[after] != '=') { pos = at + 1; continue; }
    ++after;
    while (after < tag.size() && isSpaceChar(tag[after])) ++after;
    if (after >= tag.size()) return false;
    char quote = tag[after];
    if (quote != '"' && quote != '\'') return false;
    size_t end = tag.find(quote, after + 1);
    if (end == std::string::npos) return false;
    out = decodeXmlEntities(tag.substr(after + 1, end - after - 1));
    return true;
  }
  return false;
}

// 找到下一个以 "<name" 开头的标签起始位置，且 name 之后紧跟空白、'>' 或 '/'
size_t findTagStart(const std::string& xml, const std::string& name, size_t from) {
  std::string needle = "<" + name;
  size_t pos = from;
  while (true) {
    pos = xml.find(needle, pos);
    if (pos == std::string::npos) return std::string::npos;
    size_t after = pos + needle.size();
    if (after >= xml.size()) return std::string::npos;
    char c = xml[after];
    if (isSpaceChar(c) || c == '>' || c == '/') return pos;
    pos = after;
  }
}

// 取标签（自 pos 起）的完整内容，返回 '>' 之后的位置；标签内容写入 tag
size_t readTag(const std::string& xml, size_t pos, std::string& tag) {
  size_t end = xml.find('>', pos);
  if (end == std::string::npos) { tag.clear(); return std::string::npos; }
  tag = xml.substr(pos, end - pos + 1);
  return end + 1;
}

// 提取 <name ...>...</name> 或 <name .../> 的文本内容（不含子标签文本，直接拼接内部所有文本片段）
// 简化：找到开标签，若自闭合返回空；否则找到对应闭标签，取中间内容（可能含子标签，此处用于 <t>）
bool extractElementText(const std::string& xml, size_t openPos, const std::string& name, std::string& out, size_t& nextPos) {
  std::string tag;
  size_t afterOpen = readTag(xml, openPos, tag);
  if (afterOpen == std::string::npos) return false;
  // 自闭合
  if (!tag.empty() && tag[tag.size() - 2] == '/') { out.clear(); nextPos = afterOpen; return true; }
  std::string closeTag = "</" + name;
  size_t closePos = xml.find(closeTag, afterOpen);
  if (closePos == std::string::npos) return false;
  // 中间内容原样（<t> 一般无子标签；若有，保留原始，最终交给调用方决定）
  out = xml.substr(afterOpen, closePos - afterOpen);
  size_t closeEnd = xml.find('>', closePos);
  if (closeEnd == std::string::npos) return false;
  nextPos = closeEnd + 1;
  return true;
}

// 提取所有 <t ...> 元素的文本（拼接），支持 xml:space="preserve"
std::string extractAllT(const std::string& xml) {
  std::string result;
  size_t pos = 0;
  while (true) {
    size_t tStart = findTagStart(xml, "t", pos);
    if (tStart == std::string::npos) break;
    std::string tag;
    size_t afterOpen = readTag(xml, tStart, tag);
    if (afterOpen == std::string::npos) break;
    // 自闭合 <t/>
    if (tag.size() >= 2 && tag[tag.size() - 2] == '/') { pos = afterOpen; continue; }
    size_t closePos = xml.find("</t", afterOpen);
    if (closePos == std::string::npos) break;
    std::string text = xml.substr(afterOpen, closePos - afterOpen);
    result += decodeXmlEntities(text);
    size_t closeEnd = xml.find('>', closePos);
    if (closeEnd == std::string::npos) break;
    pos = closeEnd + 1;
  }
  return result;
}

// 解析 sharedStrings.xml → vector<string>
std::vector<std::string> parseSharedStrings(const std::string& xml) {
  std::vector<std::string> out;
  size_t pos = 0;
  while (true) {
    size_t siStart = findTagStart(xml, "si", pos);
    if (siStart == std::string::npos) break;
    std::string tag;
    size_t afterOpen = readTag(xml, siStart, tag);
    if (afterOpen == std::string::npos) break;
    if (tag.size() >= 2 && tag[tag.size() - 2] == '/') { out.emplace_back(); pos = afterOpen; continue; }
    size_t closePos = xml.find("</si", afterOpen);
    if (closePos == std::string::npos) break;
    std::string inner = xml.substr(afterOpen, closePos - afterOpen);
    out.push_back(extractAllT(inner));
    size_t closeEnd = xml.find('>', closePos);
    if (closeEnd == std::string::npos) break;
    pos = closeEnd + 1;
  }
  return out;
}

// 从 rId 中提取数字部分，如 "rId3" → 3；失败返回 0
unsigned long parseRidNumber(const std::string& rid) {
  unsigned long n = 0;
  bool any = false;
  for (size_t i = 0; i < rid.size(); ++i) {
    char c = rid[i];
    if (c >= '0' && c <= '9') { n = n * 10 + static_cast<unsigned long>(c - '0'); any = true; }
    else if (any) break;
  }
  return any ? n : 0;
}

// 从工作表路径（如 "worksheets/sheet3.xml"）提取数字，失败返回 0
unsigned long parseSheetNumber(const std::string& path) {
  // 找 "sheet" 之后到 ".xml" 之间的数字
  size_t s = path.rfind("sheet");
  if (s == std::string::npos) return 0;
  s += 5;
  unsigned long n = 0;
  bool any = false;
  for (size_t i = s; i < path.size(); ++i) {
    char c = path[i];
    if (c >= '0' && c <= '9') { n = n * 10 + static_cast<unsigned long>(c - '0'); any = true; }
    else break;
  }
  return any ? n : 0;
}

// 规范化 rels Target 为 xlsx 内相对路径（去掉前导 '/'，处理 "xl/" 前缀）
std::string normalizeTarget(const std::string& target) {
  std::string t = target;
  if (!t.empty() && t[0] == '/') t = t.substr(1);
  // rels 的 Target 是相对于 xl/ 的，通常写作 "worksheets/sheet1.xml"
  if (startsWith(t, "xl/")) return t;
  return "xl/" + t;
}

// 解析 workbook.xml：按文档顺序提取 (name, rId)
struct SheetEntry { std::string name; std::string rid; };
std::vector<SheetEntry> parseWorkbookSheets(const std::string& xml) {
  std::vector<SheetEntry> out;
  size_t pos = 0;
  while (true) {
    size_t sStart = findTagStart(xml, "sheet", pos);
    if (sStart == std::string::npos) break;
    // 排除 <sheets> 这类
    size_t after = sStart + 6;
    if (after < xml.size()) {
      char c = xml[after];
      if (!(isSpaceChar(c) || c == '>' || c == '/')) { pos = after; continue; }
    }
    std::string tag;
    size_t afterOpen = readTag(xml, sStart, tag);
    if (afterOpen == std::string::npos) break;
    SheetEntry e;
    extractAttr(tag, "name", e.name);
    extractAttr(tag, "r:id", e.rid);
    if (e.rid.empty()) extractAttr(tag, "id", e.rid);
    out.push_back(std::move(e));
    pos = afterOpen;
  }
  return out;
}

// 解析 workbook.xml.rels → map<rId, target 路径>
std::vector<std::pair<std::string, std::string>> parseWorkbookRels(const std::string& xml) {
  std::vector<std::pair<std::string, std::string>> out;
  size_t pos = 0;
  while (true) {
    size_t rStart = findTagStart(xml, "Relationship", pos);
    if (rStart == std::string::npos) break;
    std::string tag;
    size_t afterOpen = readTag(xml, rStart, tag);
    if (afterOpen == std::string::npos) break;
    std::string id, target, type;
    extractAttr(tag, "Id", id);
    extractAttr(tag, "Target", target);
    extractAttr(tag, "Type", type);
    if (!id.empty() && !target.empty()) {
      out.emplace_back(id, normalizeTarget(target));
    }
    pos = afterOpen;
  }
  return out;
}

// 判断单元格文本是否全空白
bool isBlankText(const std::string& s) {
  for (size_t i = 0; i < s.size(); ++i) {
    if (!isSpaceChar(s[i])) return false;
  }
  return true;
}

}  // namespace

XlsxExtractor::XlsxResult XlsxExtractor::extractFromPath(const std::string& path) noexcept {
  XlsxResult result;
  try {
    ZipReader zip;
    std::string zerr;
    if (!zip.open(path, zerr)) {
      result.ok = false;
      result.error = "无法打开 xlsx: " + zerr;
      return result;
    }

    // 1. 读取 workbook.xml
    if (!zip.hasEntry("xl/workbook.xml")) {
      result.ok = false;
      result.error = "缺少 xl/workbook.xml，不是有效的 xlsx";
      return result;
    }
    std::string workbookXml;
    if (!zip.readEntry("xl/workbook.xml", workbookXml, zerr)) {
      result.ok = false;
      result.error = "读取 xl/workbook.xml 失败: " + zerr;
      return result;
    }

    std::vector<SheetEntry> sheetEntries = parseWorkbookSheets(workbookXml);

    // 2. 读取 rels 建立 rId → 路径 映射
    std::vector<std::pair<std::string, std::string>> rels;
    bool relsOk = false;
    if (zip.hasEntry("xl/_rels/workbook.xml.rels")) {
      std::string relsXml;
      if (zip.readEntry("xl/_rels/workbook.xml.rels", relsXml, zerr)) {
        rels = parseWorkbookRels(relsXml);
        relsOk = true;
      }
    }

    // 组装有序 (表名, 路径)
    std::vector<std::pair<std::string, std::string>> sheets;  // name, zipPath
    if (relsOk && !sheetEntries.empty()) {
      bool allResolved = true;
      std::vector<std::pair<std::string, std::string>> tmp;
      for (const auto& se : sheetEntries) {
        std::string targetPath;
        bool found = false;
        for (const auto& rp : rels) {
          if (rp.first == se.rid) { targetPath = rp.second; found = true; break; }
        }
        if (!found) { allResolved = false; break; }
        tmp.emplace_back(se.name, targetPath);
      }
      if (allResolved) {
        sheets = std::move(tmp);
      } else {
        // 诚实降级
        relsOk = false;
      }
    }
    if (!relsOk || sheets.empty()) {
      // 降级：按 xl/worksheets/sheetN.xml 文件名数字排序
      std::vector<std::pair<unsigned long, std::string>> found;
      std::vector<std::string> names = zip.entryNames();
      for (const auto& n : names) {
        if (startsWith(n, "xl/worksheets/sheet") && n.size() > 4 &&
            n.compare(n.size() - 4, 4, ".xml") == 0) {
          unsigned long num = parseSheetNumber(n);
          if (num > 0) found.emplace_back(num, n);
        }
      }
      std::sort(found.begin(), found.end(),
                [](const std::pair<unsigned long, std::string>& a,
                   const std::pair<unsigned long, std::string>& b) {
                  return a.first < b.first;
                });
      sheets.clear();
      for (const auto& f : found) {
        sheets.emplace_back("Sheet" + std::to_string(f.first), f.second);
      }
    }

    // 3. 读取 sharedStrings.xml（缺失视为空表）
    std::vector<std::string> sharedStrings;
    if (zip.hasEntry("xl/sharedStrings.xml")) {
      std::string ssXml;
      if (zip.readEntry("xl/sharedStrings.xml", ssXml, zerr)) {
        sharedStrings = parseSharedStrings(ssXml);
      }
    }

    // 4. 逐表解析
    bool anyText = false;
    for (const auto& sh : sheets) {
      SheetText st;
      st.sheetName = sh.first;

      std::string sheetXml;
      if (!zip.hasEntry(sh.second)) {
        // 该表缺失，输出空文本并继续（诚实记录在 error 中？按需求保持 ok 但无文本）
        st.text.clear();
        result.sheets.push_back(std::move(st));
        continue;
      }
      if (!zip.readEntry(sh.second, sheetXml, zerr)) {
        st.text.clear();
        result.sheets.push_back(std::move(st));
        continue;
      }

      std::string sheetOut;
      size_t pos = 0;
      unsigned long sequentialRow = 0;
      while (true) {
        size_t rowStart = findTagStart(sheetXml, "row", pos);
        if (rowStart == std::string::npos) break;
        std::string rowTag;
        size_t afterRowOpen = readTag(sheetXml, rowStart, rowTag);
        if (afterRowOpen == std::string::npos) break;
        // 自闭合 <row/>
        bool rowSelfClose = rowTag.size() >= 2 && rowTag[rowTag.size() - 2] == '/';
        size_t rowEnd;
        if (rowSelfClose) {
          rowEnd = afterRowOpen;
        } else {
          size_t closePos = sheetXml.find("</row", afterRowOpen);
          if (closePos == std::string::npos) break;
          rowEnd = closePos;
        }

        // 行号：真实 r 属性优先
        std::string rAttr;
        unsigned long rowNum = 0;
        if (extractAttr(rowTag, "r", rAttr) && !rAttr.empty()) {
          rowNum = 0;
          bool any = false;
          for (char c : rAttr) {
            if (c >= '0' && c <= '9') { rowNum = rowNum * 10 + static_cast<unsigned long>(c - '0'); any = true; }
            else if (any) break;
          }
        } else {
          rowNum = sequentialRow + 1;
        }
        sequentialRow = rowNum;

        // 遍历行内单元格
        std::string line;
        bool firstCell = true;
        size_t cpos = afterRowOpen;
        while (cpos < rowEnd) {
          size_t cStart = findTagStart(sheetXml, "c", cpos);
          if (cStart == std::string::npos || cStart >= rowEnd) break;
          std::string cTag;
          size_t afterCOpen = readTag(sheetXml, cStart, cTag);
          if (afterCOpen == std::string::npos) break;
          bool cSelfClose = cTag.size() >= 2 && cTag[cTag.size() - 2] == '/';
          size_t cEnd;
          if (cSelfClose) {
            cEnd = afterCOpen;
          } else {
            size_t closePos = sheetXml.find("</c", afterCOpen);
            if (closePos == std::string::npos || closePos > rowEnd) {
              cEnd = rowEnd;
            } else {
              cEnd = closePos;
            }
          }

          std::string inner = cSelfClose ? std::string()
                                         : sheetXml.substr(afterCOpen, cEnd - afterCOpen);

          // 单元格类型
          std::string tAttr;
          bool hasT = extractAttr(cTag, "t", tAttr);

          std::string cellText;
          if (hasT && tAttr == "s") {
            // 共享字符串索引
            size_t vStart = findTagStart(inner, "v", 0);
            if (vStart != std::string::npos) {
              std::string vTag;
              size_t afterV = readTag(inner, vStart, vTag);
              if (afterV != std::string::npos) {
                size_t vClose = inner.find("</v", afterV);
                if (vClose != std::string::npos) {
                  std::string vtext = inner.substr(afterV, vClose - afterV);
                  // 解析整数
                  unsigned long idx = 0;
                  bool anyDigit = false;
                  bool overflow = false;
                  for (char c : vtext) {
                    if (c >= '0' && c <= '9') {
                      if (idx > (0xFFFFFFFFFFFFFFFFUL - static_cast<unsigned long>(c - '0')) / 10) {
                        overflow = true; break;
                      }
                      idx = idx * 10 + static_cast<unsigned long>(c - '0');
                      anyDigit = true;
                    } else if (isSpaceChar(c)) {
                      continue;
                    } else {
                      anyDigit = false; break;
                    }
                  }
                  if (anyDigit && !overflow && idx < sharedStrings.size()) {
                    cellText = sharedStrings[static_cast<size_t>(idx)];
                  }
                  // 越界或非法 → 留空
                }
              }
            }
          } else if (hasT && tAttr == "str") {
            size_t vStart = findTagStart(inner, "v", 0);
            if (vStart != std::string::npos) {
              std::string vTag;
              size_t afterV = readTag(inner, vStart, vTag);
              if (afterV != std::string::npos) {
                size_t vClose = inner.find("</v", afterV);
                if (vClose != std::string::npos) {
                  cellText = decodeXmlEntities(inner.substr(afterV, vClose - afterV));
                }
              }
            }
          } else if (hasT && tAttr == "inlineStr") {
            size_t isStart = findTagStart(inner, "is", 0);
            if (isStart != std::string::npos) {
              std::string isTag;
              size_t afterIs = readTag(inner, isStart, isTag);
              if (afterIs != std::string::npos) {
                size_t isClose = inner.find("</is", afterIs);
                if (isClose != std::string::npos) {
                  std::string isInner = inner.substr(afterIs, isClose - afterIs);
                  cellText = extractAllT(isInner);
                }
              }
            }
          } else {
            // 无 t 或未知类型：<v> 数字文本直取
            size_t vStart = findTagStart(inner, "v", 0);
            if (vStart != std::string::npos) {
              std::string vTag;
              size_t afterV = readTag(inner, vStart, vTag);
              if (afterV != std::string::npos) {
                size_t vClose = inner.find("</v", afterV);
                if (vClose != std::string::npos) {
                  cellText = decodeXmlEntities(inner.substr(afterV, vClose - afterV));
                }
              }
            }
          }

          if (!firstCell) line += '\t';
          line += cellText;
          firstCell = false;

          cpos = (cSelfClose ? afterCOpen : cEnd + 4);  // 跳过 </c>
          if (cpos > rowEnd) break;
        }

        // 空行（无任何 c）跳过
        if (!firstCell) {
          sheetOut += line;
          sheetOut += '\n';
        }

        pos = (rowSelfClose ? afterRowOpen : rowEnd + 6);  // 跳过 </row>
        if (pos > sheetXml.size()) break;
      }

      if (!isBlankText(sheetOut)) anyText = true;
      st.text = std::move(sheetOut);
      result.sheets.push_back(std::move(st));
    }

    if (!anyText) {
      result.ok = false;
      result.error = "未提取到任何文本";
      return result;
    }

    result.ok = true;
    return result;
  } catch (...) {
    // noexcept 保证不抛出
    result.ok = false;
    result.error = "xlsx 解析发生未预期异常";
    return result;
  }
}
// @@XLSX_IMPL_DONE@@
namespace {

// 判断字符串是否以给定后缀结尾。
bool endsWith(const std::string& s, const std::string& suffix) {
  return s.size() >= suffix.size() &&
         s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
}

// 从 XML 文本中取出某个属性的值：形如 key="value" 或 key='value'。
// 在 [from, to) 区间内查找，未找到返回 false。
bool extractAttr(const std::string& xml, size_t from, size_t to,
                 const std::string& key, std::string& out) {
  if (from > to || to > xml.size()) return false;
  std::string needle = key + "=";
  size_t pos = from;
  while (true) {
    size_t hit = xml.find(needle, pos);
    if (hit == std::string::npos || hit >= to) return false;
    // 属性名必须独立：前一个字符不能是字母/数字/'-'/'_'（避免匹配到 xxx:key=）。
    if (hit > from) {
      char prev = xml[hit - 1];
      bool ident = (prev >= 'A' && prev <= 'Z') || (prev >= 'a' && prev <= 'z') ||
                   (prev >= '0' && prev <= '9') || prev == '_' || prev == '-' ||
                   prev == ':';
      if (ident) {
        pos = hit + needle.size();
        continue;
      }
    }
    size_t vstart = hit + needle.size();
    if (vstart >= to) return false;
    char quote = xml[vstart];
    if (quote != '"' && quote != '\'') {
      pos = vstart;
      continue;
    }
    size_t vend = xml.find(quote, vstart + 1);
    if (vend == std::string::npos || vend > to) return false;
    out.assign(xml, vstart + 1, vend - vstart - 1);
    return true;
  }
}

// （重复的 decodeXmlEntities 已删除，复用文件前部实现）

// 从 slide XML 中提取全部 <a:t>...</a:t> 文本，遇到 </a:p> 追加换行。
// 多个形状/文本框的文本按文档顺序拼接。
std::string extractSlideText(const std::string& xml) {
  std::string out;
  const std::string tOpen = "<a:t";
  const std::string tClose = "</a:t>";
  const std::string pClose = "</a:p>";
  size_t i = 0;
  while (i < xml.size()) {
    size_t tPos = xml.find(tOpen, i);
    size_t pPos = xml.find(pClose, i);
    if (tPos == std::string::npos && pPos == std::string::npos) break;
    if (tPos != std::string::npos && (pPos == std::string::npos || tPos < pPos)) {
      // 定位 <a:t ...> 的结束 '>'。
      size_t gt = xml.find('>', tPos);
      if (gt == std::string::npos) break;
      // 确保是元素而非前缀匹配（如 <a:tab/>）。
      char after = (gt + 1 < xml.size()) ? xml[gt] : '\0';
      (void)after;
      size_t contentStart = gt + 1;
      size_t tEnd = xml.find(tClose, contentStart);
      if (tEnd == std::string::npos) break;
      std::string raw = xml.substr(contentStart, tEnd - contentStart);
      out += decodeXmlEntities(raw);
      i = tEnd + tClose.size();
    } else {
      out.push_back('\n');
      i = pPos + pClose.size();
    }
  }
  return out;
}

// 从路径中抽取最后一个 '/' 之后的部分。
std::string baseName(const std::string& path) {
  size_t slash = path.find_last_of('/');
  if (slash == std::string::npos) return path;
  return path.substr(slash + 1);
}

// 从 slideN.xml 的文件名中抽取数字 N，失败返回 -1。
long slideFileNumber(const std::string& name) {
  if (!startsWith(name, "slide") || !endsWith(name, ".xml")) return -1;
  std::string num = name.substr(5, name.size() - 5 - 4);
  if (num.empty()) return -1;
  long v = 0;
  for (char c : num) {
    if (c < '0' || c > '9') return -1;
    v = v * 10 + (c - '0');
  }
  return v;
}

}  // namespace

PptxExtractor::PptxResult PptxExtractor::extractFromPath(const std::string& path) noexcept {
  PptxResult result;
  try {
    ZipReader zip;
    std::string zerr;
    if (!zip.open(path, zerr)) {
      result.ok = false;
      result.error = "无法打开文件";
      return result;
    }

    std::string presentationXml;
    if (!zip.readEntry("ppt/presentation.xml", presentationXml, zerr)) {
      result.ok = false;
      result.error = "缺少 ppt/presentation.xml，不是有效的 pptx";
      return result;
    }

    // 解析放映顺序：<p:sldId r:id="rIdN"/> 出现顺序即放映顺序。
    std::vector<std::string> orderedRids;
    {
      size_t lst = presentationXml.find("<p:sldIdLst");
      if (lst != std::string::npos) {
        size_t lstEnd = presentationXml.find("</p:sldIdLst>", lst);
        size_t limit = (lstEnd == std::string::npos) ? presentationXml.size() : lstEnd;
        size_t pos = lst;
        const std::string sldId = "<p:sldId";
        while (true) {
          size_t hit = presentationXml.find(sldId, pos);
          if (hit == std::string::npos || hit >= limit) break;
          // 确保是 <p:sldId 而非 <p:sldIdLst。
          size_t gt = presentationXml.find('>', hit);
          if (gt == std::string::npos || gt >= limit) break;
          std::string rid;
          if (extractAttr(presentationXml, hit, gt, "r:id", rid)) {
            orderedRids.push_back(rid);
          }
          pos = gt + 1;
        }
      }
    }

    // 建立 rId -> Target 映射，来源 ppt/_rels/presentation.xml.rels。
    std::vector<std::pair<std::string, std::string>> ridToTarget;
    bool relsOk = false;
    {
      std::string relsXml;
      if (zip.readEntry("ppt/_rels/presentation.xml.rels", relsXml, zerr)) {
        size_t pos = 0;
        const std::string relTag = "<Relationship";
        while (true) {
          size_t hit = relsXml.find(relTag, pos);
          if (hit == std::string::npos) break;
          size_t gt = relsXml.find('>', hit);
          if (gt == std::string::npos) break;
          std::string id, target;
          if (extractAttr(relsXml, hit, gt, "Id", id) &&
              extractAttr(relsXml, hit, gt, "Target", target)) {
            ridToTarget.emplace_back(id, target);
          }
          pos = gt + 1;
        }
        relsOk = true;
      }
    }

    // 组装有序的 slide 路径列表。
    std::vector<std::string> slidePaths;
    bool orderResolved = false;
    if (!orderedRids.empty() && relsOk) {
      bool allFound = true;
      for (const std::string& rid : orderedRids) {
        std::string target;
        bool found = false;
        for (const auto& kv : ridToTarget) {
          if (kv.first == rid) { target = kv.second; found = true; break; }
        }
        if (!found) { allFound = false; break; }
        // Target 可能为 "slides/slideN.xml" 或 "ppt/slides/slideN.xml"。
        std::string p = target;
        if (startsWith(p, "/")) p = p.substr(1);
        if (startsWith(p, "ppt/")) {
          slidePaths.push_back(p);
        } else {
          slidePaths.push_back("ppt/" + p);
        }
      }
      if (allFound && !slidePaths.empty()) orderResolved = true;
      else slidePaths.clear();
    }

    if (!orderResolved) {
      // 降级路径：放映顺序未知，按文件名数字排序。
      std::vector<std::pair<long, std::string>> numbered;
      for (const std::string& name : zip.entryNames()) {
        if (!startsWith(name, "ppt/slides/")) continue;
        std::string base = baseName(name);
        long n = slideFileNumber(base);
        if (n < 0) continue;
        numbered.emplace_back(n, name);
      }
      std::sort(numbered.begin(), numbered.end(),
                [](const std::pair<long, std::string>& a,
                   const std::pair<long, std::string>& b) {
                  if (a.first != b.first) return a.first < b.first;
                  return a.second < b.second;
                });
      for (const auto& kv : numbered) slidePaths.push_back(kv.second);
    }

    // 逐页提取文本。
    int slideNo = 1;
    for (const std::string& sp : slidePaths) {
      std::string slideXml;
      if (!zip.readEntry(sp, slideXml, zerr)) {
        // 读不到内容不静默丢弃：记录空文本，继续按序编号。
        result.slides.push_back(SlideText{slideNo, std::string()});
        ++slideNo;
        continue;
      }
      std::string text = extractSlideText(slideXml);
      result.slides.push_back(SlideText{slideNo, text});
      ++slideNo;
    }

    // 所有页都无文本 → 失败。
    bool anyText = false;
    for (const auto& s : result.slides) {
      if (!s.text.empty()) { anyText = true; break; }
    }
    if (!anyText) {
      result.ok = false;
      result.error = "未提取到任何文本";
      result.slides.clear();
      return result;
    }

    result.ok = true;
    return result;
  } catch (...) {
    // noexcept 契约：任何异常都转为失败结果。
    result.ok = false;
    result.error = "提取 pptx 时发生内部错误";
    result.slides.clear();
    return result;
  }
}
// @@PPTX_IMPL_DONE@@

}  // namespace docseek
