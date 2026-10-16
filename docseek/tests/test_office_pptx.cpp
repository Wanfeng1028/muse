// docseek PPTX 提取器集成测试
// 手工构造最小 OOXML(zip) 夹具，经真实 PptxExtractor::extractFromPath 从磁盘提取。
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

// ---------------- pptx fixture 常量 ----------------
// 故意让放映顺序与文件名数字顺序不一致：
//   sldIdLst 顺序为 rId3 → rId2 → rId1，
//   分别指向 slide2.xml → slide1.xml → slide3.xml。
//   文件名顺序为 1,2,3，放映顺序为 2,1,3。
const char* kContentTypes =
    "<?xml version=\"1.0\"?>"
    "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
    "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
    "</Types>";

const char* kPresentationXml =
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    "<p:presentation "
    "xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" "
    "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
    "<p:sldIdLst>"
    "<p:sldId id=\"256\" r:id=\"rId3\"/>"
    "<p:sldId id=\"257\" r:id=\"rId2\"/>"
    "<p:sldId id=\"258\" r:id=\"rId1\"/>"
    "</p:sldIdLst>"
    "</p:presentation>";

const char* kPresentationRels =
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
    "<Relationship Id=\"rId1\" "
    "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide\" "
    "Target=\"slides/slide3.xml\"/>"
    "<Relationship Id=\"rId2\" "
    "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide\" "
    "Target=\"slides/slide1.xml\"/>"
    "<Relationship Id=\"rId3\" "
    "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide\" "
    "Target=\"slides/slide2.xml\"/>"
    "</Relationships>";

// slide1.xml 文本： "第一页"
const char* kSlide1Xml =
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    "<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" "
    "xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\">"
    "<p:cSld><p:spTree>"
    "<p:sp><p:txBody><a:p><a:r><a:t>第一页</a:t></a:r></a:p></p:txBody></p:sp>"
    "</p:spTree></p:cSld></p:sld>";

// slide2.xml 文本： "第二页 中文"
const char* kSlide2Xml =
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    "<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" "
    "xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\">"
    "<p:cSld><p:spTree>"
    "<p:sp><p:txBody><a:p><a:r><a:t>第二页 中文</a:t></a:r></a:p></p:txBody></p:sp>"
    "</p:spTree></p:cSld></p:sld>";

// slide3.xml 文本： "第三页"
const char* kSlide3Xml =
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    "<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" "
    "xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\">"
    "<p:cSld><p:spTree>"
    "<p:sp><p:txBody><a:p><a:r><a:t>第三页</a:t></a:r></a:p></p:txBody></p:sp>"
    "</p:spTree></p:cSld></p:sld>";

std::vector<ZipEntry> makePptxEntries() {
  return {
      {"[Content_Types].xml", kContentTypes, true},
      {"ppt/presentation.xml", kPresentationXml, true},
      {"ppt/_rels/presentation.xml.rels", kPresentationRels, true},
      {"ppt/slides/slide1.xml", kSlide1Xml, true},
      {"ppt/slides/slide2.xml", kSlide2Xml, true},
      {"ppt/slides/slide3.xml", kSlide3Xml, true},
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
class OfficePptxTest : public ::testing::Test {
 protected:
  void SetUp() override {
    tmpDir_ = ::testing::TempDir() + "docseek_pptx_test_" +
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

  std::string writePptx(const std::string& name,
                        const std::vector<ZipEntry>& entries) {
    const std::string p = path(name);
    EXPECT_TRUE(writeFile(p, buildZip(entries)));
    return p;
  }

  std::string tmpDir_;
};

// 1. 按 presentation.xml 放映顺序输出：
//    sldIdLst 顺序 rId3→rId2→rId1 = slide2→slide1→slide3，
//    所以 slides[0].text 应为 slide2 的文本、slides[1] 为 slide1、slides[2] 为 slide3。
//    若实现错误地按文件名数字排序，顺序将是 slide1→slide2→slide3。
TEST_F(OfficePptxTest, PptxExtractOrder) {
  const std::string pptx = writePptx("order.pptx", makePptxEntries());

  const docseek::PptxExtractor::PptxResult r =
      docseek::PptxExtractor::extractFromPath(pptx);

  ASSERT_TRUE(r.ok) << "error: " << r.error;
  ASSERT_EQ(r.slides.size(), 3u);

  // slideNo 按放映顺序递增 1,2,3。
  EXPECT_EQ(r.slides[0].slideNo, 1);
  EXPECT_EQ(r.slides[1].slideNo, 2);
  EXPECT_EQ(r.slides[2].slideNo, 3);

  // 文本与放映顺序配对：放映顺序第 1 页 = slide2.xml = "第二页 中文"。
  EXPECT_NE(r.slides[0].text.find("第二页"), std::string::npos);
  EXPECT_NE(r.slides[1].text.find("第一页"), std::string::npos);
  EXPECT_NE(r.slides[2].text.find("第三页"), std::string::npos);

  // 反向验证：第 1 页不应是 slide1.xml 的文本。
  EXPECT_EQ(r.slides[0].text.find("第一页"), std::string::npos);
}

// 2. 中文 a:t 完整提取。
TEST_F(OfficePptxTest, PptxChineseText) {
  const std::string pptx = writePptx("chinese.pptx", makePptxEntries());

  const docseek::PptxExtractor::PptxResult r =
      docseek::PptxExtractor::extractFromPath(pptx);

  ASSERT_TRUE(r.ok) << "error: " << r.error;

  bool foundChinese = false;
  for (const auto& s : r.slides) {
    if (s.text.find("中文") != std::string::npos) {
      foundChinese = true;
      break;
    }
  }
  EXPECT_TRUE(foundChinese);

  // 标签名不得泄漏。
  for (const auto& s : r.slides) {
    EXPECT_EQ(s.text.find("a:t"), std::string::npos);
    EXPECT_EQ(s.text.find("p:sld"), std::string::npos);
  }
}

// 3. 缺 presentation.xml：
//    实现先 readEntry("ppt/presentation.xml")，读不到即直接失败
//    （error="缺少 ppt/presentation.xml，不是有效的 pptx"），
//    不会走文件名数字排序降级路径。
TEST_F(OfficePptxTest, PptxMissingPresentation) {
  std::vector<ZipEntry> entries = {
      {"[Content_Types].xml", kContentTypes, true},
      {"ppt/slides/slide1.xml", kSlide1Xml, true},
  };
  const std::string pptx = writePptx("nopres.pptx", entries);

  const docseek::PptxExtractor::PptxResult r =
      docseek::PptxExtractor::extractFromPath(pptx);
  EXPECT_FALSE(r.ok);
  EXPECT_FALSE(r.error.empty());
  EXPECT_TRUE(r.slides.empty());
}

// 4. 随机字节不是 zip → open 失败 → ok=false，error 非空。
TEST_F(OfficePptxTest, PptxCorrupt) {
  const std::string p = path("corrupt.pptx");
  std::string garbage;
  garbage.resize(512);
  for (std::size_t i = 0; i < garbage.size(); ++i) {
    garbage[i] = static_cast<char>((i * 131 + 7) & 0xFF);
  }
  ASSERT_TRUE(writeFile(p, garbage));

  const docseek::PptxExtractor::PptxResult r =
      docseek::PptxExtractor::extractFromPath(p);
  EXPECT_FALSE(r.ok);
  EXPECT_FALSE(r.error.empty());
}

// 5. slide 无 a:t：
//    实现逐页提取，读到 slide 内容后 extractSlideText 返回空串仍 push 一个
//    SlideText{slideNo, ""}；若所有页文本都为空，则整体失败
//    （error="未提取到任何文本"），且 slides 被清空。
TEST_F(OfficePptxTest, PptxEmptySlides) {
  // 有 presentation + rels，但两个 slide 均无 a:t。
  const char* emptySlide =
      "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
      "<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" "
      "xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\">"
      "<p:cSld><p:spTree/></p:cSld></p:sld>";

  const char* relsTwoSlides =
      "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
      "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
      "<Relationship Id=\"rId1\" "
      "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide\" "
      "Target=\"slides/slide1.xml\"/>"
      "<Relationship Id=\"rId2\" "
      "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide\" "
      "Target=\"slides/slide2.xml\"/>"
      "</Relationships>";

  const char* presTwoSlides =
      "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
      "<p:presentation "
      "xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" "
      "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
      "<p:sldIdLst>"
      "<p:sldId id=\"256\" r:id=\"rId1\"/>"
      "<p:sldId id=\"257\" r:id=\"rId2\"/>"
      "</p:sldIdLst>"
      "</p:presentation>";

  std::vector<ZipEntry> entries = {
      {"[Content_Types].xml", kContentTypes, true},
      {"ppt/presentation.xml", presTwoSlides, true},
      {"ppt/_rels/presentation.xml.rels", relsTwoSlides, true},
      {"ppt/slides/slide1.xml", emptySlide, true},
      {"ppt/slides/slide2.xml", emptySlide, true},
  };
  const std::string pptx = writePptx("empty.pptx", entries);

  const docseek::PptxExtractor::PptxResult r =
      docseek::PptxExtractor::extractFromPath(pptx);
  // 所有页均无文本 → 实现判定整体失败并清空 slides。
  EXPECT_FALSE(r.ok);
  EXPECT_FALSE(r.error.empty());
  EXPECT_TRUE(r.slides.empty());
}
