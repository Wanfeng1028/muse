// docseek XlsxExtractor 单元测试
//
// 本文件不依赖任何第三方 zip 库：测试内自行手工构造最小 zip 容器，
// 经 zlib 的 compress() 做 deflate 压缩后落盘为 .xlsx，再交给
// 真正的 XlsxExtractor::extractFromPath 从磁盘文件提取。
//
// 所有写入临时目录的文件均在 TearDown 中清理。

#include <gtest/gtest.h>

#include <zlib.h>

#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "docseek/office_extractor.h"

namespace {

// ---------------------------------------------------------------------------
// 最小 zip 构造器
// ---------------------------------------------------------------------------

struct ZipEntry {
  std::string name;
  std::string data;
  bool deflate = true;
};

// 小端写入辅助函数
void appendU16(std::string& out, std::uint16_t v) {
  out.push_back(static_cast<char>(v & 0xFFu));
  out.push_back(static_cast<char>((v >> 8) & 0xFFu));
}

void appendU32(std::string& out, std::uint32_t v) {
  out.push_back(static_cast<char>(v & 0xFFu));
  out.push_back(static_cast<char>((v >> 8) & 0xFFu));
  out.push_back(static_cast<char>((v >> 16) & 0xFFu));
  out.push_back(static_cast<char>((v >> 24) & 0xFFu));
}

// 计算 zip 条目数据的 CRC32
std::uint32_t crcOf(const std::string& data) {
  const auto* buf = reinterpret_cast<const Bytef*>(data.data());
  const auto len = static_cast<uInt>(data.size());
  return static_cast<std::uint32_t>(::crc32(0L, buf, len));
}

// raw deflate 压缩（windowBits=-15，无 zlib 头/尾，与提取器 inflate 一致）
std::string deflateRaw(const std::string& data) {
  z_stream zs{};
  if (deflateInit2(&zs, Z_DEFAULT_COMPRESSION, Z_DEFLATED, -15, 8,
                   Z_DEFAULT_STRATEGY) != Z_OK) {
    return std::string();
  }
  zs.next_in = reinterpret_cast<Bytef*>(const_cast<char*>(data.data()));
  zs.avail_in = static_cast<uInt>(data.size());
  uLong bound = compressBound(static_cast<uLong>(data.size())) + 64;
  std::string buf;
  buf.resize(bound);
  zs.next_out = reinterpret_cast<Bytef*>(buf.data());
  zs.avail_out = static_cast<uInt>(buf.size());
  int rc = deflate(&zs, Z_FINISH);
  if (rc != Z_STREAM_END) {
    deflateEnd(&zs);
    return std::string();
  }
  buf.resize(buf.size() - zs.avail_out);
  deflateEnd(&zs);
  return buf;
}

// 构造完整 zip 字节流：local file header + 数据 + central directory + EOCD
std::string buildZip(const std::vector<ZipEntry>& entries) {
  std::string out;
  std::vector<std::uint32_t> localOffsets;
  localOffsets.reserve(entries.size());

  // ---- local file headers + 数据 ----
  for (const auto& e : entries) {
    localOffsets.push_back(static_cast<std::uint32_t>(out.size()));

    const std::string stored = e.deflate ? deflateRaw(e.data) : e.data;
    const std::uint16_t method = e.deflate ? 8u : 0u;
    const std::uint32_t crc = crcOf(e.data);
    const std::uint32_t compSize = static_cast<std::uint32_t>(stored.size());
    const std::uint32_t uncompSize = static_cast<std::uint32_t>(e.data.size());
    const std::uint16_t nameLen = static_cast<std::uint16_t>(e.name.size());

    appendU32(out, 0x04034b50u);  // local file header 签名
    appendU16(out, 20u);          // version needed
    appendU16(out, 0u);           // general purpose flag
    appendU16(out, method);       // compression method
    appendU16(out, 0u);           // mod time
    appendU16(out, 0u);           // mod date
    appendU32(out, crc);          // crc32
    appendU32(out, compSize);     // compressed size
    appendU32(out, uncompSize);   // uncompressed size
    appendU16(out, nameLen);      // file name length
    appendU16(out, 0u);           // extra field length
    out += e.name;
    out += stored;
  }

  // ---- central directory ----
  const std::uint32_t cdStart = static_cast<std::uint32_t>(out.size());
  for (std::size_t i = 0; i < entries.size(); ++i) {
    const auto& e = entries[i];
    const std::string stored = e.deflate ? deflateRaw(e.data) : e.data;
    const std::uint16_t method = e.deflate ? 8u : 0u;
    const std::uint32_t crc = crcOf(e.data);
    const std::uint32_t compSize = static_cast<std::uint32_t>(stored.size());
    const std::uint32_t uncompSize = static_cast<std::uint32_t>(e.data.size());
    const std::uint16_t nameLen = static_cast<std::uint16_t>(e.name.size());

    appendU32(out, 0x02014b50u);  // central directory 签名
    appendU16(out, 0x031Eu);      // made by
    appendU16(out, 20u);          // version needed
    appendU16(out, 0u);           // general purpose flag
    appendU16(out, method);       // compression method
    appendU16(out, 0u);           // mod time
    appendU16(out, 0u);           // mod date
    appendU32(out, crc);          // crc32
    appendU32(out, compSize);     // compressed size
    appendU32(out, uncompSize);   // uncompressed size
    appendU16(out, nameLen);      // file name length
    appendU16(out, 0u);           // extra field length
    appendU16(out, 0u);           // comment length
    appendU16(out, 0u);           // disk number start
    appendU16(out, 0u);           // internal attrs
    appendU32(out, 0u);           // external attrs
    appendU32(out, localOffsets[i]);  // local header offset
    out += e.name;
  }

  // ---- EOCD ----
  const std::uint32_t cdSize = static_cast<std::uint32_t>(out.size()) - cdStart;
  const std::uint16_t count = static_cast<std::uint16_t>(entries.size());

  appendU32(out, 0x06054b50u);  // EOCD 签名
  appendU16(out, 0u);           // disk number
  appendU16(out, 0u);           // cd start disk
  appendU16(out, count);        // entries on this disk
  appendU16(out, count);        // total entries
  appendU32(out, cdSize);       // central directory size
  appendU32(out, cdStart);      // central directory offset
  appendU16(out, 0u);           // comment length

  return out;
}

// ---------------------------------------------------------------------------
// xlsx fixture 内容
// ---------------------------------------------------------------------------

const char* const kWorkbookXml =
    "<?xml version=\"1.0\"?>"
    "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
    "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
    "<sheets>"
    "<sheet name=\"销售数据\" sheetId=\"1\" r:id=\"rId1\"/>"
    "<sheet name=\"Sheet2\" sheetId=\"2\" r:id=\"rId2\"/>"
    "</sheets></workbook>";

const char* const kWorkbookRelsXml =
    "<?xml version=\"1.0\"?>"
    "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
    "<Relationship Id=\"rId1\" "
    "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" "
    "Target=\"worksheets/sheet1.xml\"/>"
    "<Relationship Id=\"rId2\" "
    "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" "
    "Target=\"worksheets/sheet2.xml\"/>"
    "</Relationships>";

const char* const kSharedStringsXml =
    "<?xml version=\"1.0\"?>"
    "<sst xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
    "count=\"3\" uniqueCount=\"3\">"
    "<si><t>苹果</t></si>"
    "<si><t>香蕉</t></si>"
    "<si><t>单价</t></si>"
    "</sst>";

const char* const kSheet1Xml =
    "<?xml version=\"1.0\"?>"
    "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
    "<sheetData>"
    "<row r=\"1\"><c r=\"A1\" t=\"s\"><v>2</v></c><c r=\"B1\"><v>3.5</v></c></row>"
    "<row r=\"2\"><c r=\"A2\" t=\"s\"><v>0</v></c><c r=\"B2\" t=\"s\"><v>1</v></c></row>"
    "<row r=\"5\"><c r=\"A5\" t=\"inlineStr\"><is><t>备注文本</t></is></c></row>"
    "</sheetData></worksheet>";

const char* const kSheet2Xml =
    "<?xml version=\"1.0\"?>"
    "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
    "<sheetData>"
    "<row r=\"1\"><c r=\"A1\" t=\"str\"><v>公式计算结果</v></c></row>"
    "</sheetData></worksheet>";

// 标准 xlsx 条目集合（sheet1.xml 内容可替换，用于坏索引用例）
std::vector<ZipEntry> makeXlsxEntries(const std::string& sheet1) {
  return {
      {"xl/workbook.xml", kWorkbookXml, true},
      {"xl/_rels/workbook.xml.rels", kWorkbookRelsXml, true},
      {"xl/sharedStrings.xml", kSharedStringsXml, true},
      {"xl/worksheets/sheet1.xml", sheet1, true},
      {"xl/worksheets/sheet2.xml", kSheet2Xml, true},
  };
}

// ---------------------------------------------------------------------------
// 测试夹具：临时目录 + 落盘 + 清理
// ---------------------------------------------------------------------------

class OfficeXlsxTest : public ::testing::Test {
 protected:
  void SetUp() override {
    tmpDir_ = std::filesystem::temp_directory_path() /
              ("docseek_xlsx_test_" + std::to_string(::getpid()) + "_" +
               std::to_string(reinterpret_cast<std::uintptr_t>(this)));
    std::error_code ec;
    std::filesystem::create_directories(tmpDir_, ec);
    ASSERT_FALSE(ec) << "无法创建临时目录: " << tmpDir_.string();
  }

  void TearDown() override {
    std::error_code ec;
    std::filesystem::remove_all(tmpDir_, ec);
  }

  // 将 zip 字节流写为 .xlsx 文件并返回路径
  std::string writeXlsx(const std::string& fileName,
                        const std::vector<ZipEntry>& entries) {
    const std::filesystem::path path = tmpDir_ / fileName;
    const std::string bytes = buildZip(entries);
    std::ofstream ofs(path, std::ios::binary | std::ios::trunc);
    EXPECT_TRUE(ofs.good()) << "无法打开输出文件: " << path.string();
    ofs.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    ofs.close();
    return path.string();
  }

  std::filesystem::path tmpDir_;
};

// ---------------------------------------------------------------------------
// 测试用例
// ---------------------------------------------------------------------------

// 正常提取：两张表、表名、中文单元格、内联字符串均正确
TEST_F(OfficeXlsxTest, ExtractTwoSheets) {
  const std::string path = writeXlsx("normal.xlsx", makeXlsxEntries(kSheet1Xml));
  ASSERT_FALSE(path.empty());

  const auto result = docseek::XlsxExtractor::extractFromPath(path);
  ASSERT_TRUE(result.ok) << "提取失败: " << result.error;
  ASSERT_EQ(result.sheets.size(), 2u);

  EXPECT_EQ(result.sheets[0].sheetName, "销售数据");
  EXPECT_NE(result.sheets[0].text.find("单价"), std::string::npos);
  EXPECT_NE(result.sheets[0].text.find("3.5"), std::string::npos);
  EXPECT_NE(result.sheets[0].text.find("苹果"), std::string::npos);
  EXPECT_NE(result.sheets[0].text.find("香蕉"), std::string::npos);
  EXPECT_NE(result.sheets[0].text.find("备注文本"), std::string::npos);

  EXPECT_EQ(result.sheets[1].sheetName, "Sheet2");
  EXPECT_NE(result.sheets[1].text.find("公式计算结果"), std::string::npos);
}

// 行结构：同一行的内容必须位于同一行文本内
TEST_F(OfficeXlsxTest, RowStructure) {
  const std::string path = writeXlsx("rows.xlsx", makeXlsxEntries(kSheet1Xml));
  ASSERT_FALSE(path.empty());

  const auto result = docseek::XlsxExtractor::extractFromPath(path);
  ASSERT_TRUE(result.ok) << "提取失败: " << result.error;
  ASSERT_EQ(result.sheets.size(), 2u);

  // 将 sheet1 文本按行切分
  std::vector<std::string> lines;
  {
    std::string cur;
    for (char ch : result.sheets[0].text) {
      if (ch == '\n') {
        lines.push_back(cur);
        cur.clear();
      } else if (ch != '\r') {
        cur.push_back(ch);
      }
    }
    if (!cur.empty()) {
      lines.push_back(cur);
    }
  }

  bool headerFound = false;   // "单价" 与 "3.5" 同行
  bool dataFound = false;     // "苹果" 与 "香蕉" 同行
  for (const auto& line : lines) {
    const bool hasPrice = line.find("单价") != std::string::npos;
    const bool hasValue = line.find("3.5") != std::string::npos;
    if (hasPrice && hasValue) {
      headerFound = true;
    }
    const bool hasApple = line.find("苹果") != std::string::npos;
    const bool hasBanana = line.find("香蕉") != std::string::npos;
    if (hasApple && hasBanana) {
      dataFound = true;
    }
  }

  EXPECT_TRUE(headerFound) << "“单价”与“3.5”未出现在同一行，实际文本:\n"
                           << result.sheets[0].text;
  EXPECT_TRUE(dataFound) << "“苹果”与“香蕉”未出现在同一行，实际文本:\n"
                         << result.sheets[0].text;
}

// 缺少 workbook.xml：提取应失败
TEST_F(OfficeXlsxTest, MissingWorkbook) {
  std::vector<ZipEntry> entries = {
      {"xl/sharedStrings.xml", kSharedStringsXml, true},
  };
  const std::string path = writeXlsx("no_workbook.xlsx", entries);
  ASSERT_FALSE(path.empty());

  const auto result = docseek::XlsxExtractor::extractFromPath(path);
  EXPECT_FALSE(result.ok);
}

// 共享字符串索引越界：提取不得崩溃，坏单元格可置空或跳过
TEST_F(OfficeXlsxTest, BadSharedStringIndex) {
  // 把 sheet1.xml 中的 <v>2</v> 改为 <v>999</v>
  std::string badSheet1 = kSheet1Xml;
  const std::string from = "<v>2</v>";
  const std::string to = "<v>999</v>";
  const auto pos = badSheet1.find(from);
  ASSERT_NE(pos, std::string::npos) << "fixture 中未找到待替换的 <v>2</v>";
  badSheet1.replace(pos, from.size(), to);

  const std::string path =
      writeXlsx("bad_index.xlsx", makeXlsxEntries(badSheet1));
  ASSERT_FALSE(path.empty());

  // 只要不崩溃即可，ok 允许为 true 或 false
  const auto result = docseek::XlsxExtractor::extractFromPath(path);
  (void)result;
  SUCCEED();
}

}  // namespace
