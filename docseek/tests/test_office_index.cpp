#include <gtest/gtest.h>

#include <zlib.h>

#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/indexer.h"
#include "docseek/searcher.h"

namespace docseek {
namespace {

namespace fs = std::filesystem;

// ---------- 最小 ZIP 构造器（自实现，仅用于测试 fixture） ----------

struct ZipEntry {
  std::string name;
  std::string data;
  bool deflate = true;
};

// 以小端序把无符号整数写入缓冲区
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

// 使用 zlib compress2 进行 raw deflate 压缩（windowBits = -15）
bool rawDeflate(const std::string& input, std::string& output) {
  z_stream zs{};
  // 负数 windowBits 表示 raw deflate（不含 zlib 头与尾部校验）
  if (deflateInit2(&zs, Z_DEFAULT_COMPRESSION, Z_DEFLATED, -15, 8,
                   Z_DEFAULT_STRATEGY) != Z_OK) {
    return false;
  }
  zs.next_in = reinterpret_cast<Bytef*>(const_cast<char*>(input.data()));
  zs.avail_in = static_cast<uInt>(input.size());

  uLong bound = compressBound(static_cast<uLong>(input.size())) + 64;
  std::string buffer;
  buffer.resize(bound);

  zs.next_out = reinterpret_cast<Bytef*>(buffer.data());
  zs.avail_out = static_cast<uInt>(buffer.size());

  int rc = deflate(&zs, Z_FINISH);
  if (rc != Z_STREAM_END) {
    deflateEnd(&zs);
    return false;
  }
  size_t produced = buffer.size() - zs.avail_out;
  deflateEnd(&zs);
  buffer.resize(produced);
  output.swap(buffer);
  return true;
}

// 构造一个内存中的 ZIP 包：local file header + 文件名 + 数据，
// central directory + 文件名，最后 EOCD。
std::string buildZip(const std::vector<ZipEntry>& entries) {
  std::string out;
  struct CentralRec {
    std::string name;
    uint16_t method = 0;
    uint32_t crc = 0;
    uint32_t comp_size = 0;
    uint32_t uncomp_size = 0;
    uint32_t local_offset = 0;
  };
  std::vector<CentralRec> central;
  central.reserve(entries.size());

  for (const auto& e : entries) {
    // 计算 CRC32 与（可能压缩后的）数据体
    uint32_t crc = static_cast<uint32_t>(
        crc32(0L, reinterpret_cast<const Bytef*>(e.data.data()),
              static_cast<uInt>(e.data.size())));
    std::string body = e.data;
    uint16_t method = 0;
    if (e.deflate && !e.data.empty()) {
      std::string compressed;
      if (rawDeflate(e.data, compressed) && compressed.size() < e.data.size()) {
        body.swap(compressed);
        method = 8;
      }
    }

    CentralRec rec;
    rec.name = e.name;
    rec.method = method;
    rec.crc = crc;
    rec.comp_size = static_cast<uint32_t>(body.size());
    rec.uncomp_size = static_cast<uint32_t>(e.data.size());
    rec.local_offset = static_cast<uint32_t>(out.size());
    central.push_back(rec);

    // ---- local file header ----
    putU32(out, 0x04034b50u);                 // 签名
    putU16(out, 20);                          // 解压所需版本
    putU16(out, 0);                           // flag
    putU16(out, method);                      // 压缩方法
    putU16(out, 0);                           // 修改时间
    putU16(out, 0);                           // 修改日期
    putU32(out, crc);                         // CRC32
    putU32(out, rec.comp_size);               // 压缩后大小
    putU32(out, rec.uncomp_size);             // 未压缩大小
    putU16(out, static_cast<uint16_t>(e.name.size()));  // 文件名长度
    putU16(out, 0);                           // 扩展字段长度
    out += e.name;
    out += body;
  }

  const uint32_t cd_offset = static_cast<uint32_t>(out.size());

  // ---- central directory ----
  for (const auto& rec : central) {
    putU32(out, 0x02014b50u);                 // 签名
    putU16(out, 0x031E);                      // made by（unix）
    putU16(out, 20);                          // 解压所需版本
    putU16(out, 0);                           // flag
    putU16(out, rec.method);                  // 压缩方法
    putU16(out, 0);                           // 修改时间
    putU16(out, 0);                           // 修改日期
    putU32(out, rec.crc);                     // CRC32
    putU32(out, rec.comp_size);               // 压缩后大小
    putU32(out, rec.uncomp_size);             // 未压缩大小
    putU16(out, static_cast<uint16_t>(rec.name.size()));  // 文件名长度
    putU16(out, 0);                           // 扩展字段长度
    putU16(out, 0);                           // 注释长度
    putU16(out, 0);                           // 起始磁盘号
    putU16(out, 0);                           // 内部属性
    putU32(out, 0);                           // 外部属性
    putU32(out, rec.local_offset);            // local header 偏移
    out += rec.name;
  }

  const uint32_t cd_size = static_cast<uint32_t>(out.size()) - cd_offset;

  // ---- EOCD ----
  putU32(out, 0x06054b50u);                   // 签名
  putU16(out, 0);                             // 当前磁盘号
  putU16(out, 0);                             // central directory 起始磁盘
  putU16(out, static_cast<uint16_t>(central.size()));  // 本盘条目数
  putU16(out, static_cast<uint16_t>(central.size()));  // 总条目数
  putU32(out, cd_size);                       // central directory 大小
  putU32(out, cd_offset);                     // central directory 偏移
  putU16(out, 0);                             // 注释长度

  return out;
}

// ---------- 文件写入辅助 ----------

bool writeFile(const fs::path& path, const std::string& data) {
  std::ofstream ofs(path, std::ios::binary | std::ios::trunc);
  if (!ofs) return false;
  ofs.write(data.data(), static_cast<std::streamsize>(data.size()));
  return static_cast<bool>(ofs);
}

// ---------- Fixture：临时目录 + 打开数据库 ----------

class OfficeIndexTest : public ::testing::Test {
 protected:
  void SetUp() override {
    // 建立唯一临时目录
    fs::path base = fs::temp_directory_path();
    std::string tmpl = "docseek_office_XXXXXX";
    std::vector<char> buf(tmpl.begin(), tmpl.end());
    buf.push_back('\0');
    char* made = mkdtemp(buf.data());
    ASSERT_NE(made, nullptr) << "mkdtemp 失败";
    dir_ = fs::path(made);

    buildFixtures();

    db_ = std::make_unique<Database>(Database::open((dir_ / "index.db").string()));
  }

  void TearDown() override {
    db_.reset();
    std::error_code ec;
    fs::remove_all(dir_, ec);
  }

  // 构造四个 fixture：docx / xlsx / pptx / broken.docx
  void buildFixtures() {
    // ---- report.docx：word/document.xml 含“猕猴桃季度总结” ----
    {
      std::vector<ZipEntry> entries;
      entries.push_back({"[Content_Types].xml",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<Types xmlns=\"http://schemas.openxmlformats.org/"
                         "package/2006/content-types\">"
                         "<Default Extension=\"xml\" ContentType=\"application/"
                         "xml\"/>"
                         "<Override PartName=\"/word/document.xml\" "
                         "ContentType=\"application/vnd.openxmlformats-"
                         "officedocument.wordprocessingml.document.main+xml\"/>"
                         "</Types>",
                         true});
      entries.push_back({"_rels/.rels",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<Relationships xmlns=\"http://schemas.openxmlformats."
                         "org/package/2006/relationships\">"
                         "<Relationship Id=\"rId1\" Type=\"http://schemas."
                         "openxmlformats.org/officeDocument/2006/relationships/"
                         "officeDocument\" Target=\"word/document.xml\"/>"
                         "</Relationships>",
                         true});
      entries.push_back({"word/document.xml",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<w:document xmlns:w=\"http://schemas.openxmlformats."
                         "org/wordprocessingml/2006/main\">"
                         "<w:body><w:p><w:r><w:t>猕猴桃季度总结</w:t></w:r>"
                         "</w:p></w:body></w:document>",
                         true});
      ASSERT_TRUE(writeFile(dir_ / "report.docx", buildZip(entries)));
    }

    // ---- data.xlsx：workbook + rels + sharedStrings + sheet1 ----
    {
      std::vector<ZipEntry> entries;
      entries.push_back({"[Content_Types].xml",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<Types xmlns=\"http://schemas.openxmlformats.org/"
                         "package/2006/content-types\">"
                         "<Default Extension=\"xml\" ContentType=\"application/"
                         "xml\"/>"
                         "</Types>",
                         true});
      entries.push_back({"_rels/.rels",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<Relationships xmlns=\"http://schemas.openxmlformats."
                         "org/package/2006/relationships\">"
                         "<Relationship Id=\"rId1\" Type=\"http://schemas."
                         "openxmlformats.org/officeDocument/2006/relationships/"
                         "officeDocument\" Target=\"xl/workbook.xml\"/>"
                         "</Relationships>",
                         true});
      entries.push_back({"xl/workbook.xml",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<workbook xmlns=\"http://schemas.openxmlformats.org/"
                         "spreadsheetml/2006/main\" "
                         "xmlns:r=\"http://schemas.openxmlformats.org/"
                         "officeDocument/2006/relationships\">"
                         "<sheets><sheet name=\"水果销量\" sheetId=\"1\" "
                         "r:id=\"rId1\"/></sheets></workbook>",
                         true});
      entries.push_back({"xl/_rels/workbook.xml.rels",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<Relationships xmlns=\"http://schemas.openxmlformats."
                         "org/package/2006/relationships\">"
                         "<Relationship Id=\"rId1\" Type=\"http://schemas."
                         "openxmlformats.org/officeDocument/2006/relationships/"
                         "worksheet\" Target=\"worksheets/sheet1.xml\"/>"
                         "</Relationships>",
                         true});
      entries.push_back({"xl/sharedStrings.xml",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<sst xmlns=\"http://schemas.openxmlformats.org/"
                         "spreadsheetml/2006/main\" count=\"1\" uniqueCount=\"1\">"
                         "<si><t>火龙果</t></si></sst>",
                         true});
      entries.push_back({"xl/worksheets/sheet1.xml",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<worksheet xmlns=\"http://schemas.openxmlformats.org/"
                         "spreadsheetml/2006/main\">"
                         "<sheetData><row r=\"1\">"
                         "<c r=\"A1\" t=\"s\"><v>0</v></c>"
                         "</row></sheetData></worksheet>",
                         true});
      ASSERT_TRUE(writeFile(dir_ / "data.xlsx", buildZip(entries)));
    }

    // ---- deck.pptx：presentation + rels + slide1 ----
    {
      std::vector<ZipEntry> entries;
      entries.push_back({"[Content_Types].xml",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<Types xmlns=\"http://schemas.openxmlformats.org/"
                         "package/2006/content-types\">"
                         "<Default Extension=\"xml\" ContentType=\"application/"
                         "xml\"/>"
                         "</Types>",
                         true});
      entries.push_back({"_rels/.rels",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<Relationships xmlns=\"http://schemas.openxmlformats."
                         "org/package/2006/relationships\">"
                         "<Relationship Id=\"rId1\" Type=\"http://schemas."
                         "openxmlformats.org/officeDocument/2006/relationships/"
                         "officeDocument\" Target=\"ppt/presentation.xml\"/>"
                         "</Relationships>",
                         true});
      entries.push_back({"ppt/presentation.xml",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<p:presentation xmlns:p=\"http://schemas."
                         "openxmlformats.org/presentationml/2006/main\" "
                         "xmlns:r=\"http://schemas.openxmlformats.org/"
                         "officeDocument/2006/relationships\">"
                         "<p:sldIdLst><p:sldId id=\"256\" r:id=\"rId1\"/>"
                         "</p:sldIdLst></p:presentation>",
                         true});
      entries.push_back({"ppt/_rels/presentation.xml.rels",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<Relationships xmlns=\"http://schemas.openxmlformats."
                         "org/package/2006/relationships\">"
                         "<Relationship Id=\"rId1\" Type=\"http://schemas."
                         "openxmlformats.org/officeDocument/2006/relationships/"
                         "slide\" Target=\"slides/slide1.xml\"/>"
                         "</Relationships>",
                         true});
      entries.push_back({"ppt/slides/slide1.xml",
                         "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                         "<p:sld xmlns:p=\"http://schemas.openxmlformats.org/"
                         "presentationml/2006/main\" "
                         "xmlns:a=\"http://schemas.openxmlformats.org/drawingml/"
                         "2006/main\">"
                         "<p:cSld><p:spTree>"
                         "<p:sp><p:txBody><a:p><a:r>"
                         "<a:t>榴莲发布会</a:t>"
                         "</a:r></a:p></p:txBody></p:sp>"
                         "</p:spTree></p:cSld></p:sld>",
                         true});
      ASSERT_TRUE(writeFile(dir_ / "deck.pptx", buildZip(entries)));
    }

    // ---- broken.docx：非 ZIP 内容 ----
    ASSERT_TRUE(writeFile(dir_ / "broken.docx", "this is not a zip"));
  }

  // 判断 hits 中是否存在符合谓词的命中
  static bool anyHit(const std::vector<Hit>& hits,
                     const std::function<bool(const Hit&)>& pred) {
    for (const auto& h : hits) {
      if (pred(h)) return true;
    }
    return false;
  }

  fs::path dir_;
  std::unique_ptr<Database> db_;
};

// ---------- 用例 1：三份 Office 文件全部入库，损坏文件被跳过 ----------

TEST_F(OfficeIndexTest, IndexOfficeThreeFormats) {
  Indexer idx(*db_, IndexOptions{});
  IndexStats st = idx.indexPaths({dir_.string()});

  // 三份合法 Office 文档应被新增
  EXPECT_EQ(st.added, 3u);
  // broken.docx 应被跳过（且不中断整批）
  EXPECT_GE(st.skipped, 1u);
}

// ---------- 用例 2：docx 内容可被 FTS 命中 ----------

TEST_F(OfficeIndexTest, SearchFindsDocx) {
  Indexer idx(*db_, IndexOptions{});
  idx.indexPaths({dir_.string()});

  auto hits = db_->searchFts(Searcher::buildMatchQuery("猕猴桃"), 10);
  EXPECT_FALSE(hits.empty());

  auto endsWith = [](const std::string& s, const std::string& suffix) {
    return s.size() >= suffix.size() &&
           s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
  };
  EXPECT_TRUE(anyHit(hits, [&](const Hit& h) {
    return endsWith(h.path, "report.docx") && h.file_type == "DOCX";
  }));
}

// ---------- 用例 3：xlsx 内容可被 FTS 命中 ----------

TEST_F(OfficeIndexTest, SearchFindsXlsx) {
  Indexer idx(*db_, IndexOptions{});
  idx.indexPaths({dir_.string()});

  auto hits = db_->searchFts(Searcher::buildMatchQuery("火龙果"), 10);
  EXPECT_FALSE(hits.empty());

  auto endsWith = [](const std::string& s, const std::string& suffix) {
    return s.size() >= suffix.size() &&
           s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
  };
  EXPECT_TRUE(anyHit(hits, [&](const Hit& h) {
    return endsWith(h.path, "data.xlsx") && h.file_type == "XLSX";
  }));
}

// ---------- 用例 4：pptx 内容可被 FTS 命中 ----------

TEST_F(OfficeIndexTest, SearchFindsPptx) {
  Indexer idx(*db_, IndexOptions{});
  idx.indexPaths({dir_.string()});

  auto hits = db_->searchFts(Searcher::buildMatchQuery("榴莲"), 10);
  EXPECT_FALSE(hits.empty());

  auto endsWith = [](const std::string& s, const std::string& suffix) {
    return s.size() >= suffix.size() &&
           s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
  };
  EXPECT_TRUE(anyHit(hits, [&](const Hit& h) {
    return endsWith(h.path, "deck.pptx") && h.file_type == "PPTX";
  }));
}

// ---------- 用例 5：损坏文件不会进入数据库 ----------

TEST_F(OfficeIndexTest, BrokenDocxDoesNotBreakBatch) {
  Indexer idx(*db_, IndexOptions{});
  IndexStats st = idx.indexPaths({dir_.string()});

  // 损坏文件应当被识别（通过 errors 或 skipped 记录）
  EXPECT_TRUE(!st.errors.empty() || st.skipped >= 1u);

  // broken.docx 不应被写入数据库
  auto meta = db_->findByPath((dir_ / "broken.docx").string());
  EXPECT_FALSE(meta.has_value());
}

}  // namespace
}  // namespace docseek
