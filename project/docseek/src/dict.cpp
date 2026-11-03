#include "docseek/dict.h"

#include <cstdlib>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

#if defined(__linux__)
#include <unistd.h>
#endif

#ifndef DOCSEEK_DICT_DIR_DEFAULT
#define DOCSEEK_DICT_DIR_DEFAULT ""
#endif

namespace docseek {

namespace fs = std::filesystem;

namespace {

// 读取环境变量，若为空返回空串。
std::string getEnvNonEmpty(const char* name) {
    const char* v = std::getenv(name);
    if (v == nullptr) {
        return std::string();
    }
    return std::string(v);
}

// 通过 /proc/self/exe 获取当前可执行文件的绝对路径。
// 非 Linux 平台返回空串。
std::string getExecutablePath() {
#if defined(__linux__)
    std::vector<char> buf(4096);
    for (;;) {
        ssize_t n = ::readlink("/proc/self/exe", buf.data(), buf.size() - 1);
        if (n < 0) {
            return std::string();
        }
        if (static_cast<size_t>(n) < buf.size() - 1) {
            buf[static_cast<size_t>(n)] = '\0';
            return std::string(buf.data(), static_cast<size_t>(n));
        }
        // 缓冲区不够，加倍重试。
        buf.resize(buf.size() * 2);
    }
#else
    return std::string();
#endif
}

// 判断目录是否存在且确实是一个目录。
bool dirExists(const fs::path& p) {
    std::error_code ec;
    return fs::is_directory(p, ec);
}

}  // namespace

std::string resolveDictDir() {
    std::vector<std::string> tried;

    // 1. 环境变量
    {
        std::string env = getEnvNonEmpty("DOCSEEK_DICT_DIR");
        if (!env.empty()) {
            tried.push_back(env + " (环境变量 DOCSEEK_DICT_DIR)");
            if (dirExists(env)) {
                return fs::canonical(env).string();
            }
        } else {
            tried.push_back("(空) (环境变量 DOCSEEK_DICT_DIR 未设置)");
        }
    }

    // 可执行文件路径（可能为空）
    std::string exePath = getExecutablePath();

    if (!exePath.empty()) {
        fs::path exeDir = fs::path(exePath).parent_path();

        // 2. ../share/docseek/dict
        {
            fs::path p = exeDir / ".." / "share" / "docseek" / "dict";
            tried.push_back(p.string() + " (可执行文件上级 share 目录)");
            if (dirExists(p)) {
                return fs::canonical(p).string();
            }
        }

        // 3. ./dict
        {
            fs::path p = exeDir / "dict";
            tried.push_back(p.string() + " (可执行文件同级 dict 目录)");
            if (dirExists(p)) {
                return fs::canonical(p).string();
            }
        }
    } else {
        tried.push_back("(无法解析可执行文件路径)");
    }

    // 4. 编译期默认值
    {
        std::string def = DOCSEEK_DICT_DIR_DEFAULT;
        if (!def.empty()) {
            tried.push_back(def + " (编译期默认路径)");
            if (dirExists(def)) {
                return fs::canonical(def).string();
            }
        } else {
            tried.push_back("(空) (编译期默认路径未定义)");
        }
    }

    std::string msg = "无法定位 cppjieba 词典目录，已尝试以下路径：\n";
    for (const auto& t : tried) {
        msg += "  - " + t + "\n";
    }
    throw std::runtime_error(msg);
}

}  // namespace docseek
