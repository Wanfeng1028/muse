// tests/test_serve_r2_concurrent.cpp
// DocSeek v2 - serve 子命令并发查询契约测试 r2
// 起真实 docseek serve 进程，用真实 socket 发并发 HTTP 请求，断言响应契约（禁止 mock）。

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
class ServeFixtureConcurrent : public ::testing::Test {
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

        // 端口 = 18080 + (pid % 1000) + 文件序号偏移，防并行冲突。
        port_ = 18080 + static_cast<int>(::getpid() % 1000) + 100 * 2;

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

// 1. 16 个线程同时 GET /api/search?q=退款，全部 200 且 body 含 hits。
TEST_F(ServeFixtureConcurrent, ConcurrentSearchAllOk) {
    const int kThreads = 16;
    const int port = port_;
    std::string target = "/api/search?q=" + urlEncode("退款");
    std::atomic<int> okCount{0};
    std::atomic<int> hitsCount{0};
    std::vector<std::thread> threads;
    for (int i = 0; i < kThreads; ++i) {
        threads.emplace_back([port, target, &okCount, &hitsCount]() {
            std::string resp = httpGet(port, target);
            if (statusCode(resp) == 200) {
                okCount.fetch_add(1);
                if (resp.find("hits") != std::string::npos) {
                    hitsCount.fetch_add(1);
                }
            }
        });
    }
    for (auto& t : threads) {
        t.join();
    }
    EXPECT_EQ(okCount.load(), kThreads) << "并发搜索未全部返回 200";
    EXPECT_EQ(hitsCount.load(), kThreads) << "并发搜索响应未全部包含 hits";
}

// 2. 8 个线程混合请求 /api/search 与 /api/health，全部 200。
TEST_F(ServeFixtureConcurrent, ConcurrentMixedEndpoints) {
    const int kThreads = 8;
    const int port = port_;
    std::string searchTarget = "/api/search?q=" + urlEncode("退款");
    std::string healthTarget = "/api/health";
    std::atomic<int> okCount{0};
    std::vector<std::thread> threads;
    for (int i = 0; i < kThreads; ++i) {
        bool useSearch = (i % 2 == 0);
        threads.emplace_back([port, searchTarget, healthTarget, useSearch, &okCount]() {
            std::string resp = httpGet(port, useSearch ? searchTarget : healthTarget);
            if (statusCode(resp) == 200) {
                okCount.fetch_add(1);
            }
        });
    }
    for (auto& t : threads) {
        t.join();
    }
    EXPECT_EQ(okCount.load(), kThreads) << "混合并发请求未全部返回 200";
}

}  // namespace