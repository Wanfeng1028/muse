// tests/test_http_contract.cpp
// DocSeek v2 - serve 子命令 HTTP 契约测试
// 起真实 docseek serve 进程，用真实 socket 发 HTTP 请求，断言响应契约（禁止 mock）。

#include <gtest/gtest.h>

#include <arpa/inet.h>
#include <netinet/in.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <fcntl.h>
#include <sys/wait.h>
#include <unistd.h>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

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

// 在构建目录下创建测试临时目录 build/test-tmp/<pid>，返回绝对路径（不使用 /tmp）。
static std::string makeTempDir() {
    std::string base = "build/test-tmp";
    ::mkdir("build", 0755);
    ::mkdir(base.c_str(), 0755);
    std::string dir = base + "/" + std::to_string(static_cast<long>(::getpid()));
    ::mkdir(dir.c_str(), 0755);
    return dir;
}

// 取 docseek 二进制路径：环境变量 DOCSEEK_BIN，未设置则用 ./docseek。
static std::string docseekBin() {
    const char* env = ::getenv("DOCSEEK_BIN");
    if (env != nullptr && env[0] != '\0') {
        return std::string(env);
    }
    return std::string("./docseek");
}

// 对 UTF-8 字符串做 URL 百分号编码，非保留字符原样保留。
static std::string urlEncode(const std::string& s) {
    static const char* hex = "0123456789ABCDEF";
    std::string out;
    for (unsigned char c : s) {
        bool unreserved = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                          (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~';
        if (unreserved) {
            out.push_back(static_cast<char>(c));
        } else {
            out.push_back('%');
            out.push_back(hex[(c >> 4) & 0x0F]);
            out.push_back(hex[c & 0x0F]);
        }
    }
    return out;
}

// 写一个文本文件。
static void writeFile(const std::string& path, const std::string& content) {
    std::ofstream ofs(path, std::ios::binary);
    ofs << content;
}

// 向指定端口发送 GET 请求，返回完整原始响应。
static std::string httpGet(int port, const std::string& target) {
    std::string req = "GET " + target + " HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
    return httpRaw(port, req);
}

// 断言响应字符串中包含指定子串。
static void expectContains(const std::string& body, const std::string& needle) {
    EXPECT_NE(body.find(needle), std::string::npos) << "响应中缺少子串: " << needle << "\n响应体: " << body;
}

// 从响应中提取 HTTP 状态码（解析首行 "HTTP/1.x NNN ..."）。
static int statusCode(const std::string& resp) {
    size_t sp = resp.find(' ');
    if (sp == std::string::npos) {
        return -1;
    }
    return std::atoi(resp.c_str() + sp + 1);
}

// 测试夹具：起真实 serve 进程，跑完回收。
class ServeFixtureHttpContract : public ::testing::Test {
 protected:
    void SetUp() override {
        tmpDir_ = makeTempDir();
        docDir_ = tmpDir_ + "/docs";
        ::mkdir(docDir_.c_str(), 0755);
        dbPath_ = tmpDir_ + "/index.db";

        // 3 个中文文本文件，含可检索关键词。
        writeFile(docDir_ + "/refund.txt",
                  "退款政策说明：用户在购买后七日内可申请无理由退款，退款将原路返回。售后流程需先提交申请。");
        writeFile(docDir_ + "/aftersale.txt",
                  "售后流程指南：售后流程包含申请、审核、退款三个步骤，退款政策以本文为准。");
        writeFile(docDir_ + "/member.txt",
                  "会员说明：会员享有优先售后与专属退款政策，退款政策细节请参见退款政策文档。");

        // 用 system() 调用 docseek index 建索引。
        std::string cmd = docseekBin() + " --db " + dbPath_ + " index " + docDir_;
        int rc = std::system(cmd.c_str());
        ASSERT_EQ(rc, 0) << "建库命令失败: " << cmd;

        // 端口 = 18080 + (pid % 1000)，防冲突。
        port_ = 18080 + static_cast<int>(::getpid() % 1000);

        // fork/exec 起 serve 进程。
        pid_ = ::fork();
        ASSERT_GE(pid_, 0) << "fork 失败";
        if (pid_ == 0) {
            // 子进程：stdout/stderr 重定向到 /dev/null，exec docseek serve。
            int devnull = ::open("/dev/null", O_WRONLY);
            if (devnull >= 0) {
                ::dup2(devnull, STDOUT_FILENO);
                ::dup2(devnull, STDERR_FILENO);
                ::close(devnull);
            }
            std::string bin = docseekBin();
            std::string portStr = std::to_string(port_);
            ::execl(bin.c_str(), bin.c_str(), "--db", dbPath_.c_str(), "serve",
                    "--port", portStr.c_str(), static_cast<char*>(nullptr));
            ::_exit(127);
        }

        // 轮询 /api/health，最多 5 秒等 200。
        bool ready = false;
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
        while (std::chrono::steady_clock::now() < deadline) {
            std::string resp = httpGet(port_, "/api/health");
            if (!resp.empty() && statusCode(resp) == 200) {
                ready = true;
                break;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        ASSERT_TRUE(ready) << "serve 进程未在 5 秒内就绪，端口 " << port_;
    }

    void TearDown() override {
        if (pid_ > 0) {
            ::kill(pid_, SIGTERM);
            int status = 0;
            // 最多等 3 秒，超时则 SIGKILL。
            auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
            bool reaped = false;
            while (std::chrono::steady_clock::now() < deadline) {
                pid_t r = ::waitpid(pid_, &status, WNOHANG);
                if (r == pid_) {
                    reaped = true;
                    break;
                }
                if (r < 0) {
                    reaped = true;  // 已被回收
                    break;
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(50));
            }
            if (!reaped) {
                ::kill(pid_, SIGKILL);
                ::waitpid(pid_, &status, 0);
            }
            pid_ = -1;
        }
    }

    std::string tmpDir_;
    std::string docDir_;
    std::string dbPath_;
    int port_ = 0;
    pid_t pid_ = -1;
};

// 1. /api/health 返回 200，body 含 "ok":true 与 version。
TEST_F(ServeFixtureHttpContract, HealthContract) {
    std::string resp = httpGet(port_, "/api/health");
    EXPECT_EQ(statusCode(resp), 200) << resp;
    expectContains(resp, "\"ok\":true");
    expectContains(resp, "version");
}

// 2. /api/search 缺 q → 400，body 含 error。
TEST_F(ServeFixtureHttpContract, SearchMissingQ) {
    std::string resp = httpGet(port_, "/api/search");
    EXPECT_EQ(statusCode(resp), 400) << resp;
    expectContains(resp, "error");
}

// 3. /api/search?q=退款 → 200，hits 非空。
TEST_F(ServeFixtureHttpContract, SearchBasic) {
    std::string resp = httpGet(port_, "/api/search?q=" + urlEncode("退款"));
    EXPECT_EQ(statusCode(resp), 200) << resp;
    expectContains(resp, "hits");
    // hits 数组非空：至少有一个 hit 对象。
    expectContains(resp, "\"hits\":[{");
}

// 4. /api/search?q=退款&explain=true → body 含 base_bm25 与 final。
TEST_F(ServeFixtureHttpContract, SearchExplain) {
    std::string resp = httpGet(port_, "/api/search?q=" + urlEncode("退款") + "&explain=true");
    EXPECT_EQ(statusCode(resp), 200) << resp;
    expectContains(resp, "base_bm25");
    expectContains(resp, "final");
}

// 5. /api/search?q=退款&limit=abc → 400（新口径：非法 limit 返回 400）。
TEST_F(ServeFixtureHttpContract, SearchBadLimit) {
    std::string resp = httpGet(port_, "/api/search?q=" + urlEncode("退款") + "&limit=abc");
    EXPECT_EQ(statusCode(resp), 400) << resp;
    expectContains(resp, "error");
}

// 6. /api/search?q=退款&unknown=xyz → 200（多余参数不影响）。
TEST_F(ServeFixtureHttpContract, SearchUnknownParam) {
    std::string resp = httpGet(port_, "/api/search?q=" + urlEncode("退款") + "&unknown=xyz");
    EXPECT_EQ(statusCode(resp), 200) << resp;
    expectContains(resp, "hits");
}

// 7. /api/locate 缺 q → 400。
TEST_F(ServeFixtureHttpContract, LocateMissingQ) {
    std::string resp = httpGet(port_, "/api/locate");
    EXPECT_EQ(statusCode(resp), 400) << resp;
    expectContains(resp, "error");
}

// 8. /api/locate?q=退款政策在哪一段 → 200，含 anchors。
TEST_F(ServeFixtureHttpContract, LocateBasic) {
    std::string resp = httpGet(port_, "/api/locate?q=" + urlEncode("退款政策在哪一段"));
    EXPECT_EQ(statusCode(resp), 200) << resp;
    expectContains(resp, "anchors");
}

// 9. /api/stats → 200，含 documents 与 uptime_sec。
TEST_F(ServeFixtureHttpContract, StatsContract) {
    std::string resp = httpGet(port_, "/api/stats");
    EXPECT_EQ(statusCode(resp), 200) << resp;
    expectContains(resp, "documents");
    expectContains(resp, "uptime_sec");
}

// 10. /api/metrics → 200。
TEST_F(ServeFixtureHttpContract, MetricsPresent) {
    std::string resp = httpGet(port_, "/api/metrics");
    EXPECT_EQ(statusCode(resp), 200) << resp;
}

// 11. 未知路径 → 404。
TEST_F(ServeFixtureHttpContract, NotFound) {
    std::string resp = httpGet(port_, "/api/nope");
    EXPECT_EQ(statusCode(resp), 404) << resp;
}

// 12. POST /api/search → 405。
TEST_F(ServeFixtureHttpContract, MethodNotAllowed) {
    std::string req = "POST /api/search HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n"
                      "Content-Length: 0\r\n\r\n";
    std::string resp = httpRaw(port_, req);
    EXPECT_EQ(statusCode(resp), 405) << resp;
}

// 13. 并发冒烟：20 线程同时 GET /api/search?q=退款 全 200，之后 health 仍 200。
TEST_F(ServeFixtureHttpContract, ConcurrencySmoke) {
    const int kThreads = 20;
    std::vector<std::thread> threads;
    std::atomic<int> okCount{0};
    std::string target = "/api/search?q=" + urlEncode("退款");
    for (int i = 0; i < kThreads; ++i) {
        threads.emplace_back([this, &okCount, &target]() {
            std::string resp = httpGet(port_, target);
            if (statusCode(resp) == 200) {
                okCount.fetch_add(1);
            }
        });
    }
    for (auto& t : threads) {
        t.join();
    }
    EXPECT_EQ(okCount.load(), kThreads) << "并发搜索未全部返回 200";

    // 并发之后 health 仍 200。
    std::string resp = httpGet(port_, "/api/health");
    EXPECT_EQ(statusCode(resp), 200) << resp;
}

}  // namespace

