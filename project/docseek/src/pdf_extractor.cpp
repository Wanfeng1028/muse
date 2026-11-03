#include "docseek/pdf_extractor.h"

#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>
#include <string>
#include <vector>

namespace docseek {
namespace {

constexpr int kTimeoutMs = 30000;          // 30 秒超时
constexpr size_t kStderrLimit = 64 * 1024; // stderr 上限 64KB

std::string g_binaryOverride;  // 空串表示使用默认 "pdftotext"

std::string binaryName() {
    return g_binaryOverride.empty() ? std::string("pdftotext") : g_binaryOverride;
}

// 在 $PATH 中查找可执行文件；若 binary 已含 '/' 则直接检查
bool isExecutableInPath(const std::string& name) {
    if (name.empty()) return false;
    if (name.find('/') != std::string::npos) {
        return ::access(name.c_str(), X_OK) == 0;
    }
    const char* pathEnv = ::getenv("PATH");
    if (pathEnv == nullptr) return false;
    std::string path(pathEnv);
    size_t start = 0;
    while (start <= path.size()) {
        size_t colon = path.find(':', start);
        std::string dir = (colon == std::string::npos)
                              ? path.substr(start)
                              : path.substr(start, colon - start);
        if (!dir.empty()) {
            std::string full = dir + "/" + name;
            if (::access(full.c_str(), X_OK) == 0) return true;
        }
        if (colon == std::string::npos) break;
        start = colon + 1;
    }
    return false;
}

// 大小写不敏感子串查找
bool containsIgnoreCase(const std::string& haystack, const std::string& needle) {
    if (needle.empty()) return true;
    if (haystack.size() < needle.size()) return false;
    auto lower = [](char c) -> char {
        return (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : c;
    };
    for (size_t i = 0; i + needle.size() <= haystack.size(); ++i) {
        bool match = true;
        for (size_t j = 0; j < needle.size(); ++j) {
            if (lower(haystack[i + j]) != lower(needle[j])) {
                match = false;
                break;
            }
        }
        if (match) return true;
    }
    return false;
}

// 统计 '\f' 个数
int countFormFeed(const std::string& s) {
    int n = 0;
    for (char c : s) {
        if (c == '\f') ++n;
    }
    return n;
}

// 核心：调用 pdftotext 提取文本
PdfExtractResult runPdftotext(const std::string& path, int firstPage, int lastPage) {
    PdfExtractResult res;

    std::string bin = binaryName();
    if (!isExecutableInPath(bin)) {
        res.error = "pdftotext 不可用";
        return res;
    }

    // 构造 argv
    std::vector<std::string> args;
    args.push_back(bin);
    args.push_back("-layout");
    args.push_back("-enc");
    args.push_back("UTF-8");
    if (firstPage >= 1 && lastPage >= firstPage) {
        args.push_back("-f");
        args.push_back(std::to_string(firstPage));
        args.push_back("-l");
        args.push_back(std::to_string(lastPage));
    }
    args.push_back(path);
    args.push_back("-");

    std::vector<char*> argv;
    argv.reserve(args.size() + 1);
    for (auto& a : args) {
        argv.push_back(const_cast<char*>(a.c_str()));
    }
    argv.push_back(nullptr);

    int outPipe[2] = {-1, -1};
    int errPipe[2] = {-1, -1};
    if (::pipe(outPipe) != 0) {
        res.error = "pipe 失败";
        return res;
    }
    if (::pipe(errPipe) != 0) {
        ::close(outPipe[0]);
        ::close(outPipe[1]);
        res.error = "pipe 失败";
        return res;
    }

    pid_t pid = ::fork();
    if (pid < 0) {
        ::close(outPipe[0]);
        ::close(outPipe[1]);
        ::close(errPipe[0]);
        ::close(errPipe[1]);
        res.error = "fork 失败";
        return res;
    }

    if (pid == 0) {
        // 子进程
        ::dup2(outPipe[1], STDOUT_FILENO);
        ::dup2(errPipe[1], STDERR_FILENO);
        ::close(outPipe[0]);
        ::close(outPipe[1]);
        ::close(errPipe[0]);
        ::close(errPipe[1]);
        ::execvp(argv[0], argv.data());
        // exec 失败
        _exit(127);
    }

    // 父进程
    ::close(outPipe[1]);
    ::close(errPipe[1]);

    std::string outBuf;
    std::string errBuf;
    bool timedOut = false;

    struct pollfd fds[2];
    fds[0].fd = outPipe[0];
    fds[0].events = POLLIN;
    fds[0].revents = 0;
    fds[1].fd = errPipe[0];
    fds[1].events = POLLIN;
    fds[1].revents = 0;

    bool outDone = false;
    bool errDone = false;

    while (!outDone || !errDone) {
        fds[0].revents = 0;
        fds[1].revents = 0;
        int nfds = 0;
        if (!outDone) {
            fds[nfds].fd = outPipe[0];
            fds[nfds].events = POLLIN;
            ++nfds;
        }
        if (!errDone) {
            fds[nfds].fd = errPipe[0];
            fds[nfds].events = POLLIN;
            ++nfds;
        }
        if (nfds == 0) break;

        int pr = ::poll(fds, static_cast<nfds_t>(nfds), kTimeoutMs);
        if (pr < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (pr == 0) {
            timedOut = true;
            break;
        }

        for (int i = 0; i < nfds; ++i) {
            if (fds[i].revents & (POLLIN | POLLHUP | POLLERR)) {
                int fd = fds[i].fd;
                char buf[8192];
                ssize_t n = ::read(fd, buf, sizeof(buf));
                if (n > 0) {
                    if (fd == outPipe[0]) {
                        outBuf.append(buf, static_cast<size_t>(n));
                    } else if (errBuf.size() < kStderrLimit) {
                        size_t room = kStderrLimit - errBuf.size();
                        size_t take = static_cast<size_t>(n) < room ? static_cast<size_t>(n) : room;
                        errBuf.append(buf, take);
                    }
                } else if (n == 0) {
                    if (fd == outPipe[0]) outDone = true;
                    else errDone = true;
                } else {
                    if (errno != EINTR && errno != EAGAIN) {
                        if (fd == outPipe[0]) outDone = true;
                        else errDone = true;
                    }
                }
            }
        }
    }

    ::close(outPipe[0]);
    ::close(errPipe[0]);

    if (timedOut) {
        ::kill(pid, SIGKILL);
    }

    int status = 0;
    while (::waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR) break;
    }

    if (timedOut) {
        res.error = "提取超时";
        return res;
    }

    int exitCode = -1;
    if (WIFEXITED(status)) {
        exitCode = WEXITSTATUS(status);
    } else if (WIFSIGNALED(status)) {
        exitCode = 128 + WTERMSIG(status);
    }

    if (exitCode != 0) {
        bool enc = false;
        if (containsIgnoreCase(errBuf, "Incorrect password") ||
            containsIgnoreCase(errBuf, "may not be copied") ||
            containsIgnoreCase(errBuf, "encrypt")) {
            enc = true;
        }
        if (enc) {
            res.encrypted = true;
            res.error = "PDF 已加密";
        } else {
            std::string head = errBuf.substr(0, 200);
            res.error = "pdftotext 退出码 " + std::to_string(exitCode);
            if (!head.empty()) res.error += "：" + head;
        }
        return res;
    }

    res.text = std::move(outBuf);
    int ff = countFormFeed(res.text);
    if (ff > 0) {
        res.pages = ff;
    } else if (!res.text.empty()) {
        res.pages = 1;
    } else {
        res.pages = 0;
    }
    res.ok = true;
    return res;
}

}  // namespace

PdfExtractResult PdfExtractor::extractFromPath(const std::string& path) noexcept {
    try {
        return runPdftotext(path, 0, 0);
    } catch (...) {
        PdfExtractResult res;
        res.error = "未知异常";
        return res;
    }
}

PdfExtractResult PdfExtractor::extractPages(const std::string& path, int firstPage, int lastPage) noexcept {
    try {
        int fp = firstPage < 1 ? 1 : firstPage;
        int lp = lastPage < fp ? fp : lastPage;
        return runPdftotext(path, fp, lp);
    } catch (...) {
        PdfExtractResult res;
        res.error = "未知异常";
        return res;
    }
}

bool PdfExtractor::isAvailable() noexcept {
    try {
        return isExecutableInPath(binaryName());
    } catch (...) {
        return false;
    }
}

void PdfExtractor::setBinaryPathForTest(const std::string& p) {
    g_binaryOverride = p;
}

}  // namespace docseek
