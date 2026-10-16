// docseek DOCX 提取器集成测试
// 手工构造最小 OOXML(zip) 夹具，经真实 DocxExtractor::extractFromPath 从磁盘提取。
#include <gtest/gtest.h>

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#include <zlib.h>

#include "docseek/office_extractor.h"

namespace {

// ---------------- 小端写入辅助 ----------------
void putU16(std::string& out, uint16_t v) {
  out.push_back(static_cast<char>(v & 0xFF));
  out.push_back(static_cast<char>((v >> 8) & 0xFF));
}

void putU32(std::string& out, uint32_t v) {
  out.push_back(static_cast<char>(v & 0xFF));
  out.push_back(static_cast<char>((v >> 8) & 0xFF));
  out.push_back(static_cast<char>((v >> 16) & 0xFF));
  out.push_back(static_cast<char>((v >> 24) & 0xFF));
}

// ---------------- zip 条目定义 ----------------
struct ZipEntry {
  std::string name;
  std::string data;
  bool deflate = true;
};

// raw deflate 压缩（windowBits=-15，无 zlib 头/尾，与提取器 inflate 一致）
std::string deflateData(const std::string& raw) {
  z_stream zs{};
  if (deflateInit2(&zs, Z_DEFAULT_COMPRESSION, Z_DEFLATED, -15, 8,
                   Z_DEFAULT_STRATEGY) != Z_OK) {
    return std::string();
  }
  zs.next_in = reinterpret_cast<Bytef*>(const_cast<char*>(raw.data()));
  zs.avail_in = static_cast<uInt>(raw.size());
  uLong bound = compressBound(static_cast<uLong>(raw.size())) + 64;
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

// 构造最小 zip 字节流：local file header + data + central directory + EOCD
std::string buildZip(const std::vector<ZipEntry>& entries) {
  std::string body;      // local headers + data
  std::string central;   // central directory
  uint32_t count = 0;

  for (const ZipEntry& e : entries) {
    const uint32_t nameLen = static_cast<uint32_t>(e.name.size());
    const uint32_t offset = static_cast<uint32_t>(body.size());

    std::string stored;
    uint16_t method = 0;
    if (e.deflate) {
      stored = deflateData(e.data);
      method = 8;
    } else {
      stored = e.data;
      method = 0;
    }

    const uLong crc = crc32(0L, reinterpret_cast<const Bytef*>(e.data.data()),
                            static_cast<uInt>(e.data.size()));
    const uint32_t compSize = static_cast<uint32_t>(stored.size());
    const uint32_t uncompSize = static_cast<uint32_t>(e.data.size());

    // local file header
    putU32(body, 0x04034b50u);
    putU16(body, 20);          // version needed
    putU16(body, 0);           // flags
    putU16(body, method);      // compression method
    putU16(body, 0);           // mod time
    putU16(body, 0);           // mod date
    putU32(body, static_cast<uint32_t>(crc));
    putU32(body, compSize);
    putU32(body, uncompSize);
    putU16(body, static_cast<uint16_t>(nameLen));
    putU16(body, 0);           // extra len
    body += e.name;
    body += stored;

    // central directory record
    putU32(central, 0x02014b50u);
    putU16(central, 0x031E);   // made by
    putU16(central, 20);       // version needed
    putU16(central, 0);        // flags
    putU16(central, method);   // method
    putU16(central, 0);        // time
    putU16(central, 0);        // date
    putU32(central, static_cast<uint32_t>(crc));
    putU32(central, compSize);
    putU32(central, uncompSize);
    putU16(central, static_cast<uint16_t>(nameLen));
    putU16(central, 0);        // extra len
    putU16(central, 0);        // comment len
    putU16(central, 0);        // disk number
    putU16(central, 0);        // internal attrs
    putU32(central, 0);        // external attrs
    putU32(central, offset);   // local header offset
    central += e.name;

    ++count;
  }

  const uint32_t cdOffset = static_cast<uint32_t>(body.size());
  const uint32_t cdSize = static_cast<uint32_t>(central.size());

  std::string out = body;
  out += central;

  // EOCD
  putU32(out, 0x06054b50u);
  putU16(out, 0);              // disk number
  putU16(out, 0);              // disk with cd
  putU16(out, static_cast<uint16_t>(count));
  putU16(out, static_cast<uint16_t>(count));
  putU32(out, cdSize);
  putU32(out, cdOffset);
  putU16(out, 0);              // comment len

  return out;
}

// ---------------- docx fixture 常量 ----------------
const char* kContentTypes =
    "<?xml version=\"1.0\"?>"
    "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
    "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
    "</Types>";

const char* kRels =
    "<?xml version=\"1.0\"?>"
    "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
    "<Relationship Id=\"rId1\" "
    "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" "
    "Target=\"word/document.xml\"/>"
    "</Relationships>";

const char* kDocumentXml =
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>\n"
    "<w:p><w:r><w:t>你好世界</w:t></w:r></w:p>\n"
    "<w:p><w:r><w:t xml:space=\"preserve\">首尾空格 </w:t></w:r><w:r><w:t>保留</w:t></w:r></w:p>\n"
    "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>单元格A1</w:t></w:r></w:p></w:tc>"
    "<w:tc><w:p><w:r><w:t>单元格B1</w:t></w:r></w:p></w:tc></w:tr></w:tbl>\n"
    "<w:p><w:r><w:t>Fish &amp; Chips &#x4E2D;&#25991;</w:t></w:r></w:p>\n"
    "</w:body></w:document>";

const char* kHeaderXml =
    "<?xml version=\"1.0\"?>"
    "<w:hdr xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
    "<w:p><w:r><w:t>机密页眉</w:t></w:r></w:p></w:hdr>";

std::vector<ZipEntry> makeDocxEntries() {
  return {
      {"[Content_Types].xml", kContentTypes, true},
      {"_rels/.rels", kRels, true},
      {"word/document.xml", kDocumentXml, true},
      {"word/header1.xml", kHeaderXml, true},
  };
}

bool writeFile(const std::string& path, const std::string& bytes) {
  std::ofstream os(path, std::ios::binary);
  if (!os) {
    return false;
  }
  os.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  return static_cast<bool>(os);
}

}  // namespace

// ---------------- fixture ----------------
class OfficeDocxTest : public ::testing::Test {
 protected:
  void SetUp() override {
    tmpDir_ = ::testing::TempDir() + "docseek_docx_test_" +
              std::to_string(::testing::UnitTest::GetInstance()
                                 ->current_test_info()
                                 ->line()) +
              "/";
    std::string mk = "mkdir -p '" + tmpDir_ + "'";
    ASSERT_EQ(std::system(mk.c_str()), 0);
  }

  void TearDown() override {
    std::string rm = "rm -rf '" + tmpDir_ + "'";
    std::system(rm.c_str());
  }

  std::string path(const std::string& name) const { return tmpDir_ + name; }

  // 写 docx 夹具，返回路径
  std::string writeDocx(const std::string& name,
                        const std::vector<ZipEntry>& entries) {
    const std::string p = path(name);
    EXPECT_TRUE(writeFile(p, buildZip(entries)));
    return p;
  }

  std::string tmpDir_;
};

// 1. 中文、表格、页眉、实体解码、标签不泄漏、xml:space 保留
TEST_F(OfficeDocxTest, ExtractChineseTableHeader) {
  const std::string docx = writeDocx("sample.docx", makeDocxEntries());

  const docseek::OfficeExtractResult r =
      docseek::DocxExtractor::extractFromPath(docx);

  ASSERT_TRUE(r.ok) << "error: " << r.error;
  EXPECT_TRUE(r.error.empty());

  // 正文中文
  EXPECT_NE(r.text.find("你好世界"), std::string::npos);
  // 表格单元格
  EXPECT_NE(r.text.find("单元格A1"), std::string::npos);
  EXPECT_NE(r.text.find("单元格B1"), std::string::npos);
  // 页眉
  EXPECT_NE(r.text.find("机密页眉"), std::string::npos);
  // XML 实体：&amp; 与 &#x4E2D;&#25991; 解码
  EXPECT_NE(r.text.find("Fish & Chips"), std::string::npos);
  EXPECT_NE(r.text.find("中文"), std::string::npos);
  // 标签名不得泄漏
  EXPECT_EQ(r.text.find("w:document"), std::string::npos);
  EXPECT_EQ(r.text.find("w:t"), std::string::npos);
  // xml:space="preserve"：尾部空格被保留，跨 run 拼接后为 "首尾空格 保留"
  EXPECT_NE(r.text.find("首尾空格 保留"), std::string::npos);
}

// 2. 非 zip 文件
TEST_F(OfficeDocxTest, NotAZip) {
  const std::string p = path("notzip.docx");
  ASSERT_TRUE(writeFile(p, std::string("hello not zip")));

  const docseek::OfficeExtractResult r =
      docseek::DocxExtractor::extractFromPath(p);
  EXPECT_FALSE(r.ok);
  EXPECT_FALSE(r.error.empty());
}

// 3. 缺少 word/document.xml
TEST_F(OfficeDocxTest, MissingDocumentXml) {
  std::vector<ZipEntry> entries = {
      {"[Content_Types].xml", kContentTypes, true},
  };
  const std::string docx = writeDocx("nodoc.docx", entries);

  const docseek::OfficeExtractResult r =
      docseek::DocxExtractor::extractFromPath(docx);
  EXPECT_FALSE(r.ok);
}

// 4. 损坏的 deflate 数据：定位 document.xml 的压缩数据并改写中间 20 字节
TEST_F(OfficeDocxTest, CorruptDeflate) {
  std::string zip = buildZip(makeDocxEntries());
  const std::string target = "word/document.xml";

  // 解析 local file header 找到 document.xml 的压缩数据区
  std::size_t pos = 0;
  bool found = false;
  while (pos + 30 <= zip.size()) {
    const uint32_t sig = static_cast<uint8_t>(zip[pos]) |
                         (static_cast<uint32_t>(static_cast<uint8_t>(zip[pos + 1])) << 8) |
                         (static_cast<uint32_t>(static_cast<uint8_t>(zip[pos + 2])) << 16) |
                         (static_cast<uint32_t>(static_cast<uint8_t>(zip[pos + 3])) << 24);
    if (sig != 0x04034b50u) {
      break;
    }
    const uint16_t nameLen = static_cast<uint8_t>(zip[pos + 26]) |
                             (static_cast<uint16_t>(static_cast<uint8_t>(zip[pos + 27])) << 8);
    const uint16_t extraLen = static_cast<uint8_t>(zip[pos + 28]) |
                              (static_cast<uint16_t>(static_cast<uint8_t>(zip[pos + 29])) << 8);
    const uint32_t compSize = static_cast<uint8_t>(zip[pos + 18]) |
                              (static_cast<uint32_t>(static_cast<uint8_t>(zip[pos + 19])) << 8) |
                              (static_cast<uint32_t>(static_cast<uint8_t>(zip[pos + 20])) << 16) |
                              (static_cast<uint32_t>(static_cast<uint8_t>(zip[pos + 21])) << 24);
    const std::string name = zip.substr(pos + 30, nameLen);
    const std::size_t dataOff = pos + 30 + nameLen + extraLen;
    if (name == target) {
      ASSERT_GE(compSize, 20u);
      const std::size_t mid = dataOff + compSize / 2 - 10;
      for (std::size_t i = 0; i < 20 && mid + i < zip.size(); ++i) {
        zip[mid + i] = static_cast<char>(0xFF);
      }
      found = true;
      break;
    }
    pos = dataOff + compSize;
  }
  ASSERT_TRUE(found) << "document.xml entry not located";

  const std::string p = path("corrupt.docx");
  ASSERT_TRUE(writeFile(p, zip));

  const docseek::OfficeExtractResult r =
      docseek::DocxExtractor::extractFromPath(p);
  EXPECT_FALSE(r.ok);
}

// 5. ZipReader::open 对非 zip 文件返回 false
TEST_F(OfficeDocxTest, ZipReaderOpenBadFile) {
  const std::string p = path("bad.bin");
  ASSERT_TRUE(writeFile(p, std::string("definitely not a zip file")));

  docseek::ZipReader reader;
  std::string error;
  EXPECT_FALSE(reader.open(p, error));
}
