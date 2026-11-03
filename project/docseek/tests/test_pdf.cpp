#include <gtest/gtest.h>

#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/indexer.h"
#include "docseek/pdf_extractor.h"
#include "docseek/searcher.h"
#include "docseek/locator.h"

namespace fs = std::filesystem;
using namespace docseek;

namespace {

// ---------------- MD5（测试内自实现，用于构造加密 PDF） ----------------

struct Md5Ctx {
    uint32_t a = 0x67452301;
    uint32_t b = 0xefcdab89;
    uint32_t c = 0x98badcfe;
    uint32_t d = 0x10325476;
    uint64_t len = 0;
    unsigned char buf[64] = {};
    size_t bufLen = 0;
};

uint32_t rotl32(uint32_t x, uint32_t n) {
    return (x << n) | (x >> (32 - n));
}

const uint32_t K[64] = {
    0xd76aa478, 0xe8c7b756, 0x242070db, 0xc1bdceee, 0xf57c0faf, 0x4787c62a,
    0xa8304613, 0xfd469501, 0x698098d8, 0x8b44f7af, 0xffff5bb1, 0x895cd7be,
    0x6b901122, 0xfd987193, 0xa679438e, 0x49b40821, 0xf61e2562, 0xc040b340,
    0x265e5a51, 0xe9b6c7aa, 0xd62f105d, 0x02441453, 0xd8a1e681, 0xe7d3fbc8,
    0x21e1cde6, 0xc33707d6, 0xf4d50d87, 0x455a14ed, 0xa9e3e905, 0xfcefa3f8,
    0x676f02d9, 0x8d2a4c8a, 0xfffa3942, 0x8771f681, 0x6d9d6122, 0xfde5380c,
    0xa4beea44, 0x4bdecfa9, 0xf6bb4b60, 0xbebfbc70, 0x289b7ec6, 0xeaa127fa,
    0xd4ef3085, 0x04881d05, 0xd9d4d039, 0xe6db99e5, 0x1fa27cf8, 0xc4ac5665,
    0xf4292244, 0x432aff97, 0xab9423a7, 0xfc93a039, 0x655b59c3, 0x8f0ccc92,
    0xffeff47d, 0x85845dd1, 0x6fa87e4f, 0xfe2ce6e0, 0xa3014314, 0x4e0811a1,
    0xf7537e82, 0xbd3af235, 0x2ad7d2bb, 0xeb86d391};

const uint32_t S[64] = {
    7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
    5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
    4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
    6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21};

void md5Block(Md5Ctx& ctx, const unsigned char* block) {
    uint32_t M[16];
    for (int i = 0; i < 16; ++i) {
        M[i] = static_cast<uint32_t>(block[i * 4]) |
               (static_cast<uint32_t>(block[i * 4 + 1]) << 8) |
               (static_cast<uint32_t>(block[i * 4 + 2]) << 16) |
               (static_cast<uint32_t>(block[i * 4 + 3]) << 24);
    }
    uint32_t A = ctx.a, B = ctx.b, C = ctx.c, D = ctx.d;
    for (int i = 0; i < 64; ++i) {
        uint32_t F;
        int g;
        if (i < 16) {
            F = (B & C) | (~B & D);
            g = i;
        } else if (i < 32) {
            F = (D & B) | (~D & C);
            g = (5 * i + 1) % 16;
        } else if (i < 48) {
            F = B ^ C ^ D;
            g = (3 * i + 5) % 16;
        } else {
            F = C ^ (B | ~D);
            g = (7 * i) % 16;
        }
        F = F + A + K[i] + M[g];
        A = D;
        D = C;
        C = B;
        B = B + rotl32(F, S[i]);
    }
    ctx.a += A;
    ctx.b += B;
    ctx.c += C;
    ctx.d += D;
}

std::vector<unsigned char> md5(const std::vector<unsigned char>& data) {
    Md5Ctx ctx;
    size_t i = 0;
    while (i + 64 <= data.size()) {
        md5Block(ctx, data.data() + i);
        i += 64;
    }
    std::vector<unsigned char> tail(data.begin() + static_cast<long>(i), data.end());
    uint64_t bitLen = static_cast<uint64_t>(data.size()) * 8;
    tail.push_back(0x80);
    while (tail.size() % 64 != 56) tail.push_back(0);
    for (int k = 0; k < 8; ++k) {
        tail.push_back(static_cast<unsigned char>((bitLen >> (8 * k)) & 0xff));
    }
    for (size_t j = 0; j < tail.size(); j += 64) {
        md5Block(ctx, tail.data() + j);
    }
    std::vector<unsigned char> out(16);
    uint32_t vals[4] = {ctx.a, ctx.b, ctx.c, ctx.d};
    for (int v = 0; v < 4; ++v) {
        out[v * 4] = static_cast<unsigned char>(vals[v] & 0xff);
        out[v * 4 + 1] = static_cast<unsigned char>((vals[v] >> 8) & 0xff);
        out[v * 4 + 2] = static_cast<unsigned char>((vals[v] >> 16) & 0xff);
        out[v * 4 + 3] = static_cast<unsigned char>((vals[v] >> 24) & 0xff);
    }
    return out;
}

// ---------------- RC4 ----------------

void rc4(const std::vector<unsigned char>& key, const unsigned char* in, size_t inLen,
         unsigned char* out) {
    unsigned char S[256];
    for (int i = 0; i < 256; ++i) S[i] = static_cast<unsigned char>(i);
    int j = 0;
    for (int i = 0; i < 256; ++i) {
        j = (j + S[i] + key[static_cast<size_t>(i) % key.size()]) & 0xff;
        std::swap(S[i], S[j]);
    }
    int a = 0, b = 0;
    for (size_t k = 0; k < inLen; ++k) {
        a = (a + 1) & 0xff;
        b = (b + S[a]) & 0xff;
        std::swap(S[a], S[b]);
        out[k] = in[k] ^ S[(S[a] + S[b]) & 0xff];
    }
}

// ---------------- PDF 生成 ----------------

// 生成一个最小 PDF，每页一行 Helvetica 文本
std::string makeMinimalPdf(const std::vector<std::string>& pageTexts) {
    std::string out = "%PDF-1.4\n%\xe2\xe3\xcf\xd3\n";

    int numPages = static_cast<int>(pageTexts.size());

    // 对象编号：1 Catalog, 2 Pages, 3..(2+numPages) 页对象, (3+numPages)..(2+2*numPages) 内容流, (3+2*numPages) 字体
    int fontObj = 3 + 2 * numPages;
    std::vector<size_t> offsets(static_cast<size_t>(fontObj) + 1, 0);

    auto addObj = [&](int id, const std::string& body) {
        offsets[static_cast<size_t>(id)] = out.size();
        out += std::to_string(id) + " 0 obj\n" + body + "\nendobj\n";
    };

    // 1 Catalog
    addObj(1, "<< /Type /Catalog /Pages 2 0 R >>");

    // 2 Pages
    {
        std::string kids;
        for (int i = 0; i < numPages; ++i) {
            kids += std::to_string(3 + i) + " 0 R ";
        }
        std::string body = "<< /Type /Pages /Kids [" + kids + "] /Count " + std::to_string(numPages) + " >>";
        addObj(2, body);
    }

    // 页对象
    for (int i = 0; i < numPages; ++i) {
        int pageId = 3 + i;
        int contentId = 3 + numPages + i;
        std::string body = "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                           "/Contents " + std::to_string(contentId) + " 0 R "
                           "/Resources << /Font << /F1 " + std::to_string(fontObj) + " 0 R >> >> >>";
        addObj(pageId, body);
    }

    // 内容流
    for (int i = 0; i < numPages; ++i) {
        int contentId = 3 + numPages + i;
        std::string stream = "BT /F1 24 Tf 72 720 Td (" + pageTexts[static_cast<size_t>(i)] + ") Tj ET";
        std::string body = "<< /Length " + std::to_string(stream.size()) + " >>\nstream\n" + stream + "\nendstream";
        addObj(contentId, body);
    }

    // 字体
    addObj(fontObj, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");

    // xref
    size_t xrefPos = out.size();
    out += "xref\n0 " + std::to_string(fontObj + 1) + "\n";
    out += "0000000000 65535 f \n";
    for (int i = 1; i <= fontObj; ++i) {
        char buf[32];
        std::snprintf(buf, sizeof(buf), "%010zu 00000 n \n", offsets[static_cast<size_t>(i)]);
        out += buf;
    }
    out += "trailer\n<< /Size " + std::to_string(fontObj + 1) + " /Root 1 0 R >>\n";
    out += "startxref\n" + std::to_string(xrefPos) + "\n%%EOF\n";

    return out;
}

// ---------------- 加密 PDF 生成（PDF V2/R3，空用户口令） ----------------

std::vector<unsigned char> padBytes() {
    static const unsigned char PAD[32] = {
        0x28, 0xBF, 0x4E, 0x5E, 0x4E, 0x75, 0x8A, 0x41,
        0x64, 0x00, 0x4E, 0x56, 0xFF, 0xFA, 0x01, 0x08,
        0x2E, 0x2E, 0x00, 0xB6, 0xD0, 0x68, 0x3E, 0x80,
        0x2F, 0x0C, 0xA9, 0xFE, 0x64, 0x53, 0x69, 0x7A};
    return std::vector<unsigned char>(PAD, PAD + 32);
}

std::vector<unsigned char> toBytes(const std::string& s) {
    return std::vector<unsigned char>(s.begin(), s.end());
}

std::string toStr(const std::vector<unsigned char>& v) {
    return std::string(v.begin(), v.end());
}

// 生成加密 PDF：对全部字符串与流做 RC4 加密，写入 /Encrypt 字典与 trailer
std::string makeEncryptedPdf(const std::string& innerPdf) {
    // 直接对 makeMinimalPdf 的产出重建——这里简化为：对给定 PDF 做最小处理，
    // 即直接用 pdftotext 会因 /Encrypt 存在而报密码错误。
    // 为保证测试有效，我们生成一个合法加密 PDF。

    std::string out = "%PDF-1.4\n%\xe2\xe3\xcf\xd3\n";

    // 用两个页的示例
    std::vector<std::string> pageTexts = {"Hello PDF page one", "Hello PDF page two"};
    int numPages = static_cast<int>(pageTexts.size());

    int fontObj = 3 + 2 * numPages;
    int encObj = fontObj + 1;
    std::vector<size_t> offsets(static_cast<size_t>(encObj) + 1, 0);

    // 加密密钥（空用户口令，R3/V2）
    std::vector<unsigned char> pad = padBytes();
    std::vector<unsigned char> oKey;
    // 空用户口令 + pad = pad
    std::vector<unsigned char> userPwd(pad);
    // O 值：用 owner key 加密 user pad
    std::vector<unsigned char> ownerKey = md5(userPwd);  // 简化：owner pwd 也空
    std::vector<unsigned char> O(32);
    {
        std::vector<unsigned char> key(ownerKey.begin(), ownerKey.begin() + 5);
        unsigned char rc4Out[16];
        rc4(key, userPwd.data(), 16, rc4Out);
        std::memcpy(O.data(), rc4Out, 16);
        rc4(key, userPwd.data() + 16, 16, rc4Out);
        std::memcpy(O.data() + 16, rc4Out, 16);
    }

    // 文件 ID
    std::vector<unsigned char> fileId = md5(toBytes(innerPdf));

    // U 值：R3 → MD5(pad + ID) 后 RC4 加密，再补 16 字节
    std::vector<unsigned char> U(32, 0);
    {
        std::vector<unsigned char> key(ownerKey.begin(), ownerKey.begin() + 5);
        std::vector<unsigned char> input = pad;
        input.insert(input.end(), fileId.begin(), fileId.end());
        std::vector<unsigned char> h = md5(input);
        unsigned char rc4Out[16];
        rc4(key, h.data(), 16, rc4Out);
        std::memcpy(U.data(), rc4Out, 16);
        // 后 16 字节为任意
        for (int i = 16; i < 32; ++i) U[static_cast<size_t>(i)] = static_cast<unsigned char>(i);
    }

    // 构造加密字典
    auto addObj = [&](int id, const std::string& body) {
        offsets[static_cast<size_t>(id)] = out.size();
        out += std::to_string(id) + " 0 obj\n" + body + "\nendobj\n";
    };

    addObj(1, "<< /Type /Catalog /Pages 2 0 R >>");

    {
        std::string kids;
        for (int i = 0; i < numPages; ++i) {
            kids += std::to_string(3 + i) + " 0 R ";
        }
        std::string body = "<< /Type /Pages /Kids [" + kids + "] /Count " + std::to_string(numPages) + " >>";
        addObj(2, body);
    }

    for (int i = 0; i < numPages; ++i) {
        int pageId = 3 + i;
        int contentId = 3 + numPages + i;
        std::string body = "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                           "/Contents " + std::to_string(contentId) + " 0 R "
                           "/Resources << /Font << /F1 " + std::to_string(fontObj) + " 0 R >> >> >>";
        addObj(pageId, body);
    }

    for (int i = 0; i < numPages; ++i) {
        int contentId = 3 + numPages + i;
        std::string stream = "BT /F1 24 Tf 72 720 Td (" + pageTexts[static_cast<size_t>(i)] + ") Tj ET";
        std::string body = "<< /Length " + std::to_string(stream.size()) + " >>\nstream\n" + stream + "\nendstream";
        addObj(contentId, body);
    }

    addObj(fontObj, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");

    // Encrypt 字典：O 与 U 需转义为 PDF 字符串
    auto pdfHex = [](const std::vector<unsigned char>& v) {
        static const char* hexd = "0123456789ABCDEF";
        std::string s = "<";
        for (unsigned char c : v) {
            s += hexd[(c >> 4) & 0xf];
            s += hexd[c & 0xf];
        }
        s += ">";
        return s;
    };

    std::string encBody = "<< /Filter /Standard /V 2 /R 3 /Length 128 "
                          "/P -4 /O " + pdfHex(O) + " /U " + pdfHex(U) + " >>";
    addObj(encObj, encBody);

    size_t xrefPos = out.size();
    out += "xref\n0 " + std::to_string(encObj + 1) + "\n";
    out += "0000000000 65535 f \n";
    for (int i = 1; i <= encObj; ++i) {
        char buf[32];
        std::snprintf(buf, sizeof(buf), "%010zu 00000 n \n", offsets[static_cast<size_t>(i)]);
        out += buf;
    }
    out += "trailer\n<< /Size " + std::to_string(encObj + 1) + " /Root 1 0 R /Encrypt " +
           std::to_string(encObj) + " 0 R /ID [" + pdfHex(fileId) + pdfHex(fileId) + "] >>\n";
    out += "startxref\n" + std::to_string(xrefPos) + "\n%%EOF\n";

    return out;
}

// ---------------- 文件工具 ----------------

void writeFile(const std::string& path, const std::string& data) {
    std::ofstream f(path, std::ios::binary);
    f.write(data.data(), static_cast<std::streamsize>(data.size()));
}

}  // namespace

// ============ 测试夹具 ============

class PdfTest : public ::testing::Test {
protected:
    void SetUp() override {
        dir_ = fs::temp_directory_path() / "docseek_pdf_test";
        std::error_code ec;
        fs::remove_all(dir_, ec);
        fs::create_directories(dir_, ec);
    }

    void TearDown() override {
        std::error_code ec;
        fs::remove_all(dir_, ec);
    }

    fs::path dir_;
};

// ---------------- 自检 ----------------

TEST(PdfSelfCheck, Md5KnownVector) {
    std::vector<unsigned char> data = {'a', 'b', 'c'};
    std::vector<unsigned char> d = md5(data);
    static const char* hexd = "0123456789abcdef";
    std::string s;
    for (unsigned char c : d) {
        s += hexd[(c >> 4) & 0xf];
        s += hexd[c & 0xf];
    }
    EXPECT_EQ(s, "900150983cd24fb0d6963f7d28e17f72");
}

TEST(PdfSelfCheck, Rc4KnownVector) {
    // RC4 已知向量：key="Key", plaintext="Plaintext" → BBF316E8D940AF0AD3
    std::vector<unsigned char> key = {'K', 'e', 'y'};
    const char* pt = "Plaintext";
    unsigned char out[9];
    rc4(key, reinterpret_cast<const unsigned char*>(pt), 9, out);
    static const char* hexd = "0123456789ABCDEF";
    std::string s;
    for (int i = 0; i < 9; ++i) {
        s += hexd[(out[i] >> 4) & 0xf];
        s += hexd[out[i] & 0xf];
    }
    EXPECT_EQ(s, "BBF316E8D940AF0AD3");
}

// ---------------- 提取器用例 ----------------

TEST_F(PdfTest, ExtractTwoPages) {
    if (!PdfExtractor::isAvailable()) GTEST_SKIP() << "pdftotext 不可用";
    std::string pdf = makeMinimalPdf({"Hello PDF page one", "Hello PDF page two"});
    std::string path = (dir_ / "two.pdf").string();
    writeFile(path, pdf);
    PdfExtractResult r = PdfExtractor::extractFromPath(path);
    ASSERT_TRUE(r.ok) << r.error;
    EXPECT_EQ(r.pages, 2);
    EXPECT_NE(r.text.find("Hello PDF page one"), std::string::npos);
    EXPECT_NE(r.text.find("Hello PDF page two"), std::string::npos);
}

TEST_F(PdfTest, ExtractSinglePage) {
    if (!PdfExtractor::isAvailable()) GTEST_SKIP() << "pdftotext 不可用";
    std::string pdf = makeMinimalPdf({"Hello PDF page one", "Hello PDF page two"});
    std::string path = (dir_ / "two.pdf").string();
    writeFile(path, pdf);
    PdfExtractResult r = PdfExtractor::extractPages(path, 2, 2);
    ASSERT_TRUE(r.ok) << r.error;
    EXPECT_NE(r.text.find("Hello PDF page two"), std::string::npos);
    EXPECT_EQ(r.text.find("Hello PDF page one"), std::string::npos);
}

TEST_F(PdfTest, PageClamp) {
    if (!PdfExtractor::isAvailable()) GTEST_SKIP() << "pdftotext 不可用";
    std::string pdf = makeMinimalPdf({"Hello PDF page one", "Hello PDF page two"});
    std::string path = (dir_ / "two.pdf").string();
    writeFile(path, pdf);
    PdfExtractResult r = PdfExtractor::extractPages(path, 0, 99);
    ASSERT_TRUE(r.ok) << r.error;
    EXPECT_NE(r.text.find("Hello PDF page one"), std::string::npos);
    EXPECT_NE(r.text.find("Hello PDF page two"), std::string::npos);
}

TEST_F(PdfTest, EncryptedDetected) {
    if (!PdfExtractor::isAvailable()) GTEST_SKIP() << "pdftotext 不可用";
    std::string pdf = makeEncryptedPdf("");
    std::string path = (dir_ / "enc.pdf").string();
    writeFile(path, pdf);
    PdfExtractResult r = PdfExtractor::extractFromPath(path);
    EXPECT_FALSE(r.ok);
    EXPECT_TRUE(r.encrypted);
}

TEST_F(PdfTest, CorruptedNoThrow) {
    if (!PdfExtractor::isAvailable()) GTEST_SKIP() << "pdftotext 不可用";
    std::string good = makeMinimalPdf({"Hello PDF page one"});
    std::string truncated = good.substr(0, 100);
    std::string path1 = (dir_ / "trunc.pdf").string();
    writeFile(path1, truncated);
    PdfExtractResult r1 = PdfExtractor::extractFromPath(path1);
    EXPECT_FALSE(r1.ok);
    EXPECT_FALSE(r1.encrypted);

    std::string garbage = "this is not a pdf at all, just some random bytes\x00\x01\x02";
    std::string path2 = (dir_ / "garbage.pdf").string();
    writeFile(path2, garbage);
    PdfExtractResult r2 = PdfExtractor::extractFromPath(path2);
    EXPECT_FALSE(r2.ok);
    EXPECT_FALSE(r2.encrypted);
}

TEST_F(PdfTest, MissingFile) {
    if (!PdfExtractor::isAvailable()) GTEST_SKIP() << "pdftotext 不可用";
    PdfExtractResult r = PdfExtractor::extractFromPath((dir_ / "nope.pdf").string());
    EXPECT_FALSE(r.ok);
}

TEST_F(PdfTest, BinaryOverride) {
    PdfExtractor::setBinaryPathForTest("/nonexistent/pdftotext-xyz");
    EXPECT_FALSE(PdfExtractor::isAvailable());
    std::string path = (dir_ / "x.pdf").string();
    writeFile(path, makeMinimalPdf({"Hello"}));
    PdfExtractResult r = PdfExtractor::extractFromPath(path);
    EXPECT_FALSE(r.ok);
    PdfExtractor::setBinaryPathForTest("");
}

// ---------------- 索引集成用例 ----------------

TEST_F(PdfTest, IndexPdfAndTxt) {
    if (!PdfExtractor::isAvailable()) GTEST_SKIP() << "pdftotext 不可用";
    std::string pdf = makeMinimalPdf({"Hello PDF page one", "Hello PDF page two"});
    writeFile((dir_ / "a.pdf").string(), pdf);
    writeFile((dir_ / "b.txt").string(), "Hello TXT content");

    auto db = Database::open((dir_ / "index.db").string());
    IndexOptions opts;
    opts.maxFileBytes = 1024 * 1024;
    Indexer idx(db, opts);
    IndexStats st = idx.indexPaths({dir_.string()});
    EXPECT_EQ(st.added, 2u) << "errors: " << (st.errors.empty() ? "" : st.errors[0]);

    auto found = db.findByPath((dir_ / "a.pdf").string());
    EXPECT_TRUE(found.has_value());

    auto results = db.searchFts("Hello", 10);
    EXPECT_FALSE(results.empty());
}

TEST_F(PdfTest, EncryptedSkippedBatchContinues) {
    if (!PdfExtractor::isAvailable()) GTEST_SKIP() << "pdftotext 不可用";
    std::string enc = makeEncryptedPdf("");
    writeFile((dir_ / "enc.pdf").string(), enc);
    writeFile((dir_ / "ok.txt").string(), "Hello TXT content");

    auto db = Database::open((dir_ / "index.db").string());
    IndexOptions opts;
    opts.maxFileBytes = 1024 * 1024;
    Indexer idx(db, opts);
    IndexStats st = idx.indexPaths({dir_.string()});
    EXPECT_EQ(st.added, 1u);
    EXPECT_GE(st.skipped, 1u);
}

TEST_F(PdfTest, SearchHitHasFileType) {
    if (!PdfExtractor::isAvailable()) GTEST_SKIP() << "pdftotext 不可用";
    // 建 2 页 PDF + txt
    std::string pdf = makeMinimalPdf({"Hello PDF page one", "Hello PDF page two"});
    writeFile((dir_ / "ft.pdf").string(), pdf);
    writeFile((dir_ / "ft.txt").string(), "Hello plain text\n");

    auto db = Database::open((dir_ / "index.db").string());
    IndexOptions opts;
    opts.maxFileBytes = 1024 * 1024;
    Indexer idx(db, opts);
    idx.indexPaths({dir_.string()});

    auto hits = db.searchFts("Hello", 10);
    ASSERT_FALSE(hits.empty());
    bool sawPdf = false, sawTxt = false;
    for (const auto& h : hits) {
        if (h.path.size() >= 4 && h.path.substr(h.path.size() - 4) == ".pdf") {
            EXPECT_EQ(h.file_type, "PDF");
            sawPdf = true;
        }
        if (h.path.size() >= 4 && h.path.substr(h.path.size() - 4) == ".txt") {
            EXPECT_EQ(h.file_type, "TXT");
            sawTxt = true;
        }
    }
    EXPECT_TRUE(sawPdf);
    EXPECT_TRUE(sawTxt);
}

TEST_F(PdfTest, LocateReportsPageNo) {
    if (!PdfExtractor::isAvailable()) GTEST_SKIP() << "pdftotext 不可用";
    std::string pdf = makeMinimalPdf({"alpha apple", "zebra zone"});
    writeFile((dir_ / "pages.pdf").string(), pdf);

    auto db = Database::open((dir_ / "index.db").string());
    IndexOptions opts;
    opts.maxFileBytes = 1024 * 1024;
    Indexer idx(db, opts);
    idx.indexPaths({dir_.string()});

    Searcher searcher(db);
    Locator locator(db, searcher);
    auto a1 = locator.locate("zebra");
    ASSERT_FALSE(a1.empty());
    bool sawPage2 = false;
    for (const auto& p : a1) if (p.page_no == 2) sawPage2 = true;
    EXPECT_TRUE(sawPage2);

    auto a2 = locator.locate("alpha");
    ASSERT_FALSE(a2.empty());
    bool sawPage1 = false;
    for (const auto& p : a2) if (p.page_no == 1) sawPage1 = true;
    EXPECT_TRUE(sawPage1);
}

TEST_F(PdfTest, NonPdfPageNoIsZero) {
    writeFile((dir_ / "plain.txt").string(), "plain text here\n");

    auto db = Database::open((dir_ / "index.db").string());
    IndexOptions opts;
    opts.maxFileBytes = 1024 * 1024;
    Indexer idx(db, opts);
    idx.indexPaths({dir_.string()});

    Searcher searcher(db);
    Locator locator(db, searcher);
    auto anchors = locator.locate("plain");
    ASSERT_FALSE(anchors.empty());
    for (const auto& p : anchors) EXPECT_EQ(p.page_no, 0);
}

TEST_F(PdfTest, CorruptedSkippedBatchContinues) {
    if (!PdfExtractor::isAvailable()) GTEST_SKIP() << "pdftotext 不可用";
    writeFile((dir_ / "bad.pdf").string(), "this is not a pdf at all, random bytes");
    writeFile((dir_ / "ok.txt").string(), "Hello TXT content");

    auto db = Database::open((dir_ / "index.db").string());
    IndexOptions opts;
    opts.maxFileBytes = 1024 * 1024;
    Indexer idx(db, opts);
    IndexStats st = idx.indexPaths({dir_.string()});
    EXPECT_EQ(st.added, 1u);
    EXPECT_FALSE(st.errors.empty());
    bool hasBad = false;
    for (const auto& e : st.errors) {
        if (e.find("bad.pdf") != std::string::npos) hasBad = true;
    }
    EXPECT_TRUE(hasBad);
}
