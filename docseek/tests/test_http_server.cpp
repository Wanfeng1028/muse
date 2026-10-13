// tests/test_http_server.cpp
// DocSeek v2 - HttpServer 单元测试
// 使用 GoogleTest 验证 HTTP 常驻服务的基础路由、请求解析与响应行为。

#include <gtest/gtest.h>

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cstring>
#include <string>

#include "docseek/http_server.h"

namespace {

// 向指定端口发送原始 HTTP 请求字符串，并读取完整响应（直到对端关闭连接）。
// 失败时返回空字符串。
static std::string httpRaw(int port, const std::string& req) {
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        return std::string();
    }

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(static_cast<uint16_t>(port));
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);

    if (::connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        ::close(fd);
        return std::string();
    }

    // 发送全部请求字节。
    const char* data = req.data();
    size_t total = req.size();
    size_t sent = 0;
    while (sent < total) {
        ssize_t n = ::send(fd, data + sent, total - sent, 0);
        if (n <= 0) {
            ::close(fd);
            return std::string();
        }
        sent += static_cast<size_t>(n);
    }

    // 循环接收直到对端关闭。
    std::string resp;
    char buf[4096];
    for (;;) {
        ssize_t n = ::recv(fd, buf, sizeof(buf), 0);
        if (n > 0) {
            resp.append(buf, static_cast<size_t>(n));
        } else if (n == 0) {
            break;
        } else {
            // 被信号中断则重试，否则退出。
            if (errno == EINTR) {
                continue;
            }
            break;
        }
    }

    ::close(fd);
    return resp;
}

// 从 HTTP 响应字符串中解析状态码；解析失败返回 -1。
static int statusCode(const std::string& resp) {
    static const std::string prefix = "HTTP/1.1 ";
    if (resp.compare(0, prefix.size(), prefix) != 0) {
        return -1;
    }
    if (resp.size() < prefix.size() + 3) {
        return -1;
    }
    const char* p = resp.data() + prefix.size();
    if (p[0] < '0' || p[0] > '9' || p[1] < '0' || p[1] > '9' ||
        p[2] < '0' || p[2] > '9') {
        return -1;
    }
    return (p[0] - '0') * 100 + (p[1] - '0') * 10 + (p[2] - '0');
}

}  // namespace

// 测试夹具：启动服务并注册若干路由。
class SrvFixture : public ::testing::Test {
protected:
    docseek::HttpServer server_;
    int port_ = 0;

    void SetUp() override {
        server_.onGet("/hello", [](const docseek::HttpRequest&) {
            return docseek::HttpResponse::text("hi");
        });

        server_.onGet("/add", [](const docseek::HttpRequest& r) {
            int a = std::stoi(r.query.at("a"));
            int b = std::stoi(r.query.at("b"));
            return docseek::HttpResponse::json(
                "{\"sum\":" + std::to_string(a + b) + "}");
        });

        server_.onPost("/echo", [](const docseek::HttpRequest& r) {
            return docseek::HttpResponse::json(
                "{\"len\":" + std::to_string(r.body.size()) + "}");
        });

        server_.start(0);
        port_ = server_.port();
    }

    void TearDown() override { server_.stop(); }
};

// 基本 GET：响应 200，body 以 "hi" 结尾，Content-Type 含 text/html。
TEST_F(SrvFixture, GetHello) {
    std::string req =
        "GET /hello HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Connection: close\r\n"
        "\r\n";
    std::string resp = httpRaw(port_, req);

    EXPECT_EQ(statusCode(resp), 200);
    // body 以 "hi" 结尾。
    ASSERT_GE(resp.size(), 2u);
    EXPECT_EQ(resp.substr(resp.size() - 2), "hi");
    // 响应头含 text/html。
    EXPECT_NE(resp.find("text/html"), std::string::npos);
}

// 查询参数解析：GET /add?a=20&b=22 → body 含 "42"。
TEST_F(SrvFixture, GetQuery) {
    std::string req =
        "GET /add?a=20&b=22 HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Connection: close\r\n"
        "\r\n";
    std::string resp = httpRaw(port_, req);

    EXPECT_EQ(statusCode(resp), 200);
    EXPECT_NE(resp.find("42"), std::string::npos);
}

// POST body 解析：Content-Length 5，body "hello" → body 含 "5"。
TEST_F(SrvFixture, PostEcho) {
    std::string body = "hello";
    std::string req =
        "POST /echo HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Content-Length: " + std::to_string(body.size()) + "\r\n"
        "Connection: close\r\n"
        "\r\n" + body;
    std::string resp = httpRaw(port_, req);

    EXPECT_EQ(statusCode(resp), 200);
    EXPECT_NE(resp.find("\"len\":5"), std::string::npos);
}

// 未知路径 → 404。
TEST_F(SrvFixture, NotFound) {
    std::string req =
        "GET /nope HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Connection: close\r\n"
        "\r\n";
    std::string resp = httpRaw(port_, req);

    EXPECT_EQ(statusCode(resp), 404);
}

// 方法不匹配 → 405。
TEST_F(SrvFixture, MethodNotAllowed) {
    std::string req =
        "POST /hello HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Content-Length: 0\r\n"
        "Connection: close\r\n"
        "\r\n";
    std::string resp = httpRaw(port_, req);

    EXPECT_EQ(statusCode(resp), 405);
}

// URL 百分号解码：a=1%30 解码为 "10"，与 b=2 相加得 12。
TEST_F(SrvFixture, UrlDecode) {
    std::string req =
        "GET /add?a=1%30&b=2 HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Connection: close\r\n"
        "\r\n";
    std::string resp = httpRaw(port_, req);

    EXPECT_EQ(statusCode(resp), 200);
    EXPECT_NE(resp.find("12"), std::string::npos);
}
