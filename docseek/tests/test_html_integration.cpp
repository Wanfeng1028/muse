// tests/test_html_integration.cpp
//
// 文溯 DocSeek HTML 集成测试
// 覆盖：HTML 索引与搜索、标题加权、script 剔除、GBK 编码端到端、定位段落、增量索引剪枝。
// 所有测试数据写入 ctest 工作目录（build 目录）下的子目录，目录名带 pid 防并发冲突。

#include <gtest/gtest.h>

#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>

#include "docseek/database.h"
#include "docseek/indexer.h"
#include "docseek/locator.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

class HtmlIntFixture : public ::testing::Test {
protected:
    fs::path dir;
    fs::path dbPath;

    void SetUp() override {
        fs::path base = fs::current_path() / "docseek_test_html_int";
        std::error_code ec;
        fs::remove_all(base, ec);
        fs::create_directories(base, ec);
        dir = base / ("case_" + std::to_string(::getpid()));
        fs::remove_all(dir, ec);
        fs::create_directories(dir, ec);
        dbPath = dir / "index.db";
    }

    void TearDown() override {
        std::error_code ec;
        fs::remove_all(dir.parent_path(), ec);
    }

    // 以二进制方式写入文件，相对 dir 拼接
    void writeFile(const std::string& rel, const std::string& content) {
        fs::path p = dir / rel;
        fs::create_directories(p.parent_path());
        std::ofstream ofs(p, std::ios::binary | std::ios::trunc);
        ASSERT_TRUE(ofs.good()) << "无法写入文件: " << p.string();
        ofs.write(content.data(), static_cast<std::streamsize>(content.size()));
        ofs.close();
        ASSERT_TRUE(ofs.good()) << "写入失败: " << p.string();
    }
};

bool endsWith(const std::string& s, const std::string& suffix) {
    if (s.size() < suffix.size()) return false;
    return s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
}

}  // namespace

// 1. HTML 索引与搜索：标题加权、多文档命中
TEST_F(HtmlIntFixture, IndexSearchHtml) {
    writeFile("page1.html",
              "<html><head><title>退款政策</title>"
              "<meta name=\"description\" content=\"退款说明\">"
              "</head><body>"
              "<p>退款流程如下：提交申请后三个工作日到账。</p>"
              "<script>埋点词xyz123</script>"
              "</body></html>");
    writeFile("page2.html",
              "<html><head><title>公司介绍</title></head><body>"
              "<p>我们也支持退款流程咨询。</p>"
              "</body></html>");
    writeFile("note.txt", "退款流程记录");

    auto db = docseek::Database::open(dbPath.string());
    docseek::IndexOptions opts;
    docseek::Indexer indexer(db, opts);
    docseek::IndexStats st = indexer.indexPaths({dir.string()});
    EXPECT_EQ(st.added, 3u);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("退款政策", 10);
    ASSERT_FALSE(hits.empty()) << "查询 '退款政策' 应有命中";
    EXPECT_EQ(hits[0].title, "退款政策");

    std::vector<docseek::Hit> flowHits = searcher.search("退款流程", 10);
    EXPECT_EQ(flowHits.size(), 3u);
}

// 2. 定位段落：自然语言问题应能定位到 page1.html 中命中段落
TEST_F(HtmlIntFixture, LocateHtml) {
    writeFile("page1.html",
              "<html><head><title>退款政策</title>"
              "<meta name=\"description\" content=\"退款说明\">"
              "</head><body>"
              "<p>退款流程如下：提交申请后三个工作日到账。</p>"
              "<script>埋点词xyz123</script>"
              "</body></html>");
    writeFile("page2.html",
              "<html><head><title>公司介绍</title></head><body>"
              "<p>我们也支持退款流程咨询。</p>"
              "</body></html>");
    writeFile("note.txt", "退款流程记录");

    auto db = docseek::Database::open(dbPath.string());
    docseek::IndexOptions opts;
    docseek::Indexer indexer(db, opts);
    docseek::IndexStats st = indexer.indexPaths({dir.string()});
    EXPECT_EQ(st.added, 3u);

    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);
    std::vector<docseek::Passage> ps = locator.locate("退款流程写在哪一段");
    ASSERT_FALSE(ps.empty()) << "定位结果不应为空";

    bool found = false;
    for (const auto& p : ps) {
        if (endsWith(p.path, "page1.html") &&
            p.text.find("退款流程") != std::string::npos) {
            found = true;
            break;
        }
    }
    EXPECT_TRUE(found) << "应存在 page1.html 且 text 含 '退款流程' 的段落";
}

// 3. script 内容不进索引
TEST_F(HtmlIntFixture, ScriptNotIndexed) {
    writeFile("page1.html",
              "<html><head><title>退款政策</title>"
              "<meta name=\"description\" content=\"退款说明\">"
              "</head><body>"
              "<p>退款流程如下：提交申请后三个工作日到账。</p>"
              "<script>埋点词xyz123</script>"
              "</body></html>");
    writeFile("page2.html",
              "<html><head><title>公司介绍</title></head><body>"
              "<p>我们也支持退款流程咨询。</p>"
              "</body></html>");
    writeFile("note.txt", "退款流程记录");

    auto db = docseek::Database::open(dbPath.string());
    docseek::IndexOptions opts;
    docseek::Indexer indexer(db, opts);
    docseek::IndexStats st = indexer.indexPaths({dir.string()});
    EXPECT_EQ(st.added, 3u);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("xyz123", 10);
    EXPECT_TRUE(hits.empty()) << "script 内容不应进入索引";
}

// 4. GBK 编码端到端：解析 charset 后正确解码标题与正文
TEST_F(HtmlIntFixture, CharsetEndToEnd) {
    // GBK 字节：测=B2 E2 试=CA D4 中=D6 D0 文=CE C4
    const std::string gbkHtml =
        "<html><head><meta charset=\"gbk\"><title>"
        "\xB2\xE2\xCA\xD4"
        "</title></head><body><p>"
        "\xD6\xD0\xCE\xC4"
        "</p></body></html>";
    writeFile("gbk.html", gbkHtml);

    auto db = docseek::Database::open(dbPath.string());
    docseek::IndexOptions opts;
    docseek::Indexer indexer(db, opts);
    docseek::IndexStats st = indexer.indexPaths({dir.string()});
    EXPECT_EQ(st.added, 1u);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("测试", 10);
    ASSERT_FALSE(hits.empty()) << "GBK 文件应可被 UTF-8 查询命中";
    EXPECT_EQ(hits[0].title, "测试");
}

// 5. 增量索引：新增、更新、删除的统计与 docCount 收敛
TEST_F(HtmlIntFixture, IncrementalPrune) {
    const std::string aPath = "a.html";

    // 第一次索引：added == 1
    writeFile(aPath,
              "<html><head><title>第一版</title></head>"
              "<body><p>初始内容。</p></body></html>");

    auto db = docseek::Database::open(dbPath.string());
    docseek::IndexOptions opts;
    docseek::Indexer indexer(db, opts);

    docseek::IndexStats st1 = indexer.indexPaths({dir.string()});
    EXPECT_EQ(st1.added, 1u);
    EXPECT_EQ(st1.updated, 0u);
    EXPECT_EQ(st1.removed, 0u);
    EXPECT_EQ(db.docCount(), 1u);

    // 改写内容并推进 mtime 5 秒：updated == 1
    writeFile(aPath,
              "<html><head><title>第二版</title></head>"
              "<body><p>内容已更新。</p></body></html>");
    {
        fs::path p = dir / aPath;
        auto t = fs::last_write_time(p);
        fs::last_write_time(p, t + std::chrono::seconds(5));
    }

    docseek::IndexStats st2 = indexer.indexPaths({dir.string()});
    EXPECT_EQ(st2.added, 0u);
    EXPECT_EQ(st2.updated, 1u);
    EXPECT_EQ(st2.removed, 0u);
    EXPECT_EQ(db.docCount(), 1u);

    // 删除文件：removed == 1，docCount 归零
    {
        std::error_code ec;
        fs::remove(dir / aPath, ec);
        ASSERT_FALSE(ec) << "删除 a.html 失败";
    }

    docseek::IndexStats st3 = indexer.indexPaths({dir.string()});
    EXPECT_EQ(st3.added, 0u);
    EXPECT_EQ(st3.updated, 0u);
    EXPECT_EQ(st3.removed, 1u);
    EXPECT_EQ(db.docCount(), 0u);
}
