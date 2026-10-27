// tests/test_serve_r2_snippet.cpp
// DocSeek v2 - serve snippet UTF-8 完整性契约测试 (r2)
// 起真实 docseek serve 进程，用真实 socket 发 HTTP 请求，断言 UTF-8 契约（禁止 mock）。

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

    std::string resp;
    char buf[4096];
    for (;;) {
        ssize_t n = ::recv(fd, buf, sizeof(buf), 0);
        if (n > 0) {
            resp.append(buf, static_cast<size_t>(n));
        } else if (n == 0) {
            break;
        } else {
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

// 按字节判断字符串是否为合法 UTF-8：逐字节校验多字节序列完整，不截断。
// 返回 true 表示整段字节序列合法 UTF-8。
static bool isValidUtf8(const std::string& s) {
    const unsigned char* p = reinterpret_cast<const unsigned char*>(s.data());
    size_t n = s.size();
    size_t i = 0;
    while (i < n) {
        unsigned char c = p[i];
        if (c < 0x80) {
            i += 1;
            continue;
        }
        size_t need = 0;
        unsigned int cp = 0;
        if ((c & 0xE0) == 0xC0) {
            need = 1;
            cp = c & 0x1F;
        } else if ((c & 0xF0) == 0xE0) {
            need = 2;
            cp = c & 0x0F;
        } else if ((c & 0xF8) == 0xF0) {
            need = 3;
            cp = c & 0x07;
        } else {
            return false;
        }
        if (i + need >= n + 0 && i + need > n - 1) {
            // 不足以容纳完整续字节
            if (i + need >= n) {
                return false;
            }
        }
        if (i + need >= n) {
            return false;
        }
        for (size_t k = 1; k <= need; ++k) {
            unsigned char cc = p[i + k];
            if ((cc & 0xC0) != 0x80) {
                return false;
            }
            cp = (cp << 6) | (cc & 0x3F);
        }
        // 拒绝过长编码与代理区/越界码点
        if (need == 1 && cp < 0x80) return false;
        if (need == 2 && cp < 0x800) return false;
        if (need == 3 && cp < 0x10000) return false;
        if (cp > 0x10FFFF) return false;
        if (cp >= 0xD800 && cp <= 0xDFFF) return false;
        i += need + 1;
    }
    return true;
}

// 提取 HTTP 响应 body（跳过头部）。
static std::string responseBody(const std::string& resp) {
    size_t pos = resp.find("\r\n\r\n");
    if (pos == std::string::npos) {
        return std::string();
    }
    return resp.substr(pos + 4);
}

// 构造一个 >2KB 的连续中文文本（无空格）。
static std::string makeLongChinese() {
    std::string unit = "退款政策说明售后流程指南会员专属服务条款";
    std::string doc;
    while (doc.size() < 4096) {
        doc += unit;
    }
    return doc;
}

// 测试夹具：起真实 serve 进程，跑完回收。
class ServeFixtureSnippet : public ::testing::Test {
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

        // 第 4 个文件：长中文文档（>2KB 连续中文无空格）。
        writeFile(docDir_ + "/long.txt", makeLongChinese());

        std::string cmd = docseekBin() + " --db " + dbPath_ + " index " + docDir_;
        int rc = std::system(cmd.c_str());
        ASSERT_EQ(rc, 0) << "建库命令失败: " << cmd;

        // 端口 = 18080 + (pid % 1000) + 200（本文件序号偏移防并行冲突）。
        port_ = 18080 + static_cast<int>(::getpid() % 1000) + 200;

        pid_ = ::fork();
        ASSERT_GE(pid_, 0) << "fork 失败";
        if (pid_ == 0) {
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
            auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
            bool reaped = false;
            while (std::chrono::steady_clock::now() < deadline) {
                pid_t r = ::waitpid(pid_, &status, WNOHANG);
                if (r == pid_) {
                    reaped = true;
                    break;
                }
                if (r < 0) {
                    reaped = true;
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

// 1. /api/search?q=<退款>：200；整个响应 body 是合法 UTF-8。
TEST_F(ServeFixtureSnippet, SearchResponseUtf8Valid) {
    std::string resp = httpGet(port_, "/api/search?q=" + urlEncode("退款"));
    EXPECT_EQ(statusCode(resp), 200) << resp;
    std::string body = responseBody(resp);
    EXPECT_FALSE(body.empty());
    EXPECT_TRUE(isValidUtf8(body)) << "响应 body 不是合法 UTF-8";
    expectContains(body, "hits");
}

// 2. 长中文文档（>2KB 连续中文无空格）搜索，响应 UTF-8 合法。
TEST_F(ServeFixtureSnippet, LongChineseSnippetUtf8Valid) {
    std::string resp = httpGet(port_, "/api/search?q=" + urlEncode("售后流程指南"));
    EXPECT_EQ(statusCode(resp), 200) << resp;
    std::string body = responseBody(resp);
    EXPECT_FALSE(body.empty());
    EXPECT_TRUE(isValidUtf8(body)) << "长中文文档搜索响应不是合法 UTF-8";
    expectContains(body, "hits");
    expectContains(body, "snippet");
}

// 3. /api/locate?q=<退款政策>&limit=3：200，anchors 非空，text/context 合法 UTF-8。
TEST_F(ServeFixtureSnippet, LocateAnchorsUtf8Valid) {
    std::string resp = httpGet(port_, "/api/locate?q=" + urlEncode("退款政策") + "&limit=3");
    EXPECT_EQ(statusCode(resp), 200) << resp;
    std::string body = responseBody(resp);
    EXPECT_FALSE(body.empty());
    EXPECT_TRUE(isValidUtf8(body)) << "locate 响应不是合法 UTF-8";
    expectContains(body, "anchors");
    expectContains(body, "\"anchors\":[{");
    expectContains(body, "text");
    expectContains(body, "context");
}

}  // namespace
