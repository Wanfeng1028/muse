// tests/test_service.cpp
// Service 端到端测试：真实 HttpServer + 真实 Database + 真实 Watcher。
#include <gtest/gtest.h>

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>

#include "docseek/database.h"
#include "docseek/service.h"

namespace fs = std::filesystem;

namespace {

// 发送原始 HTTP 请求，返回完整响应字符串。
std::string httpRaw(int port, const std::string& req) {
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return "";
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(static_cast<uint16_t>(port));
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (::connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        ::close(fd);
        return "";
    }
    size_t sent = 0;
    while (sent < req.size()) {
        ssize_t n = ::send(fd, req.data() + sent, req.size() - sent, 0);
        if (n <= 0) {
            ::close(fd);
            return "";
        }
        sent += static_cast<size_t>(n);
    }
    std::string resp;
    char buf[4096];
    while (true) {
        ssize_t n = ::recv(fd, buf, sizeof(buf), 0);
        if (n <= 0) break;
        resp.append(buf, static_cast<size_t>(n));
    }
    ::close(fd);
    return resp;
}

// 从响应中解析 HTTP 状态码，失败返回 -1。
int statusCode(const std::string& resp) {
    // 形如 "HTTP/1.1 200 OK"
    auto sp1 = resp.find(' ');
    if (sp1 == std::string::npos) return -1;
    auto sp2 = resp.find(' ', sp1 + 1);
    if (sp2 == std::string::npos) return -1;
    try {
        return std::stoi(resp.substr(sp1 + 1, sp2 - sp1 - 1));
    } catch (...) {
        return -1;
    }
}

// 简易 URL 编码（仅处理常见保留字符）。
std::string urlEncode(const std::string& s) {
    static const char* hex = "0123456789ABCDEF";
    std::string out;
    for (unsigned char c : s) {
        if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
            (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~') {
            out.push_back(static_cast<char>(c));
        } else {
            out.push_back('%');
            out.push_back(hex[(c >> 4) & 0xF]);
            out.push_back(hex[c & 0xF]);
        }
    }
    return out;
}

// 发起 GET 请求。
std::string httpGet(int port, const std::string& path) {
    std::string req = "GET " + path + " HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
    return httpRaw(port, req);
}

// 发起 POST 请求，带 JSON 正文。
std::string httpPost(int port, const std::string& path, const std::string& jsonBody) {
    std::string req = "POST " + path + " HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n";
    req += "Content-Type: application/json\r\n";
    req += "Content-Length: " + std::to_string(jsonBody.size()) + "\r\n\r\n";
    req += jsonBody;
    return httpRaw(port, req);
}

}  // namespace

// 端到端 Fixture。
class SvcFixture : public ::testing::Test {
protected:
    void SetUp() override {
        base_ = fs::temp_directory_path() / "docseek_svc_test";
        std::error_code ec;
        fs::remove_all(base_, ec);
        fs::create_directories(base_);

        // 写入测试文件。
        {
            std::ofstream f(base_ / "doc1.txt", std::ios::binary);
            f << "hello world 全文检索";
        }
        {
            std::ofstream f(base_ / "doc2.md", std::ios::binary);
            f << "# 标题\nfoo bar baz";
        }

        dbPath_ = base_ / "docseek_svc_test.db";
        fs::remove(dbPath_, ec);

        db_ = std::make_unique<docseek::Database>(docseek::Database::open(dbPath_.string()));

        docseek::ServeOptions opts;
        opts.port = 0;  // 让系统分配端口
        svc_ = std::make_unique<docseek::Service>(*db_, opts);

        runThread_ = std::thread([this] { svc_->run(); });

        // 轮询等待端口就绪，最多 5 秒。
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
        while (svc_->port() <= 0 && std::chrono::steady_clock::now() < deadline) {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
    }

    void TearDown() override {
        if (svc_) svc_->stop();
        if (runThread_.joinable()) runThread_.join();
        svc_.reset();
        db_.reset();
        std::error_code ec;
        fs::remove_all(base_, ec);
    }

    fs::path base_;
    fs::path dbPath_;
    std::unique_ptr<docseek::Database> db_;
    std::unique_ptr<docseek::Service> svc_;
    std::thread runThread_;
};

// 健康检查接口。
TEST_F(SvcFixture, Health) {
    ASSERT_GT(svc_->port(), 0);
    std::string resp = httpGet(svc_->port(), "/api/health");
    EXPECT_EQ(statusCode(resp), 200);
    EXPECT_NE(resp.find("\"ok\":true"), std::string::npos);
    EXPECT_NE(resp.find("0.4.0"), std::string::npos);
}

// 索引与检索端到端。
TEST_F(SvcFixture, IndexAndSearch) {
    ASSERT_GT(svc_->port(), 0);
    int port = svc_->port();

    std::string body = "{\"path\":\"" + base_.string() + "\"}";
    std::string resp = httpPost(port, "/api/index", body);
    EXPECT_EQ(statusCode(resp), 200);
    EXPECT_NE(resp.find("\"added\":2"), std::string::npos);

    std::string searchResp = httpGet(port, "/api/search?q=" + urlEncode("全文检索"));
    EXPECT_EQ(statusCode(searchResp), 200);
    EXPECT_NE(searchResp.find("hits"), std::string::npos);
    EXPECT_NE(searchResp.find("doc1.txt"), std::string::npos);

    // 缺少 q 参数应返回 400。
    std::string badResp = httpGet(port, "/api/search");
    EXPECT_EQ(statusCode(badResp), 400);
}

// 自然语言定位接口端到端。
TEST_F(SvcFixture, LocateApi) {
    ASSERT_GT(svc_->port(), 0);
    int port = svc_->port();

    std::string body = "{\"path\":\"" + base_.string() + "\"}";
    httpPost(port, "/api/index", body);

    std::string resp = httpGet(port, "/api/locate?q=" + urlEncode("全文检索在哪一段") + "&limit=3");
    EXPECT_EQ(statusCode(resp), 200);
    EXPECT_NE(resp.find("anchors"), std::string::npos);
    EXPECT_NE(resp.find("doc1.txt"), std::string::npos);
    EXPECT_NE(resp.find("line_start"), std::string::npos);

    // 缺少 q 参数应返回 400。
    std::string badResp = httpGet(port, "/api/locate");
    EXPECT_EQ(statusCode(badResp), 400);
}

// 统计接口。
TEST_F(SvcFixture, Stats) {
    ASSERT_GT(svc_->port(), 0);
    int port = svc_->port();

    std::string body = "{\"path\":\"" + base_.string() + "\"}";
    httpPost(port, "/api/index", body);

    std::string resp = httpGet(port, "/api/stats");
    EXPECT_EQ(statusCode(resp), 200);
    EXPECT_NE(resp.find("\"documents\":2"), std::string::npos);
    EXPECT_NE(resp.find("watched_dirs"), std::string::npos);
}

// 监控接口：添加、查询、删除。
TEST_F(SvcFixture, WatchApi) {
    ASSERT_GT(svc_->port(), 0);
    int port = svc_->port();

    std::string body = "{\"path\":\"" + base_.string() + "\"}";
    std::string addResp = httpPost(port, "/api/watch", body);
    EXPECT_EQ(statusCode(addResp), 200);
    EXPECT_NE(addResp.find("\"added\":true"), std::string::npos);

    std::string listResp = httpGet(port, "/api/watch");
    EXPECT_EQ(statusCode(listResp), 200);
    EXPECT_NE(listResp.find(base_.string()), std::string::npos);

    std::string delResp = httpGet(port, "/api/watch?path=" + urlEncode(base_.string()));
    // 删除使用 DELETE 方法更规范，这里按契约使用 DELETE。
    std::string delReq = "DELETE /api/watch?path=" + urlEncode(base_.string()) +
                         " HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
    std::string delReal = httpRaw(port, delReq);
    EXPECT_EQ(statusCode(delReal), 200);

    std::string listResp2 = httpGet(port, "/api/watch");
    EXPECT_EQ(statusCode(listResp2), 200);
    EXPECT_EQ(listResp2.find(base_.string()), std::string::npos);
    (void)delResp;
}

// Web UI 首页。
TEST_F(SvcFixture, WebUi) {
    ASSERT_GT(svc_->port(), 0);
    std::string resp = httpGet(svc_->port(), "/");
    EXPECT_EQ(statusCode(resp), 200);
    // 检查响应头中 Content-Type 是否包含 text/html。
    std::string lower = resp;
    for (auto& c : lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    EXPECT_NE(lower.find("content-type: text/html"), std::string::npos);
    EXPECT_NE(resp.find("DocSeek"), std::string::npos);
}

// 清理缺失文件。
TEST_F(SvcFixture, PruneApi) {
    ASSERT_GT(svc_->port(), 0);
    int port = svc_->port();

    std::string body = "{\"path\":\"" + base_.string() + "\"}";
    httpPost(port, "/api/index", body);

    // 删除 doc2.md 后触发 prune。
    std::error_code ec;
    fs::remove(base_ / "doc2.md", ec);

    std::string resp = httpPost(port, "/api/prune", "{}");
    EXPECT_EQ(statusCode(resp), 200);
    EXPECT_NE(resp.find("\"removed\":1"), std::string::npos);
}
