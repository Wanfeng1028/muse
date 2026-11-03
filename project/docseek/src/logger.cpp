#include "docseek/logger.h"

#include <atomic>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <mutex>
#include <string>

namespace docseek {
namespace {

// 全局日志级别，用原子量保证多线程读写安全
std::atomic<int> g_level{static_cast<int>(Level::Info)};

// 写 stderr 的全局互斥锁，串行化整行输出
std::mutex g_writeMutex;

// 当前线程的 request_id
thread_local std::string t_requestId;

// request_id 原子计数器，从 1 开始
std::atomic<unsigned long long> g_requestCounter{0};

// 将级别枚举转为小写字符串
const char* levelToString(Level lv) {
    switch (lv) {
        case Level::Debug: return "debug";
        case Level::Info:  return "info";
        case Level::Warn:  return "warn";
        case Level::Error: return "error";
    }
    return "info";
}

// 将字符串整体转为小写，用于环境变量解析
std::string toLower(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        out.push_back(static_cast<char>(
            std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

// 返回当前 UTC 时间的 ISO8601 字符串（YYYY-MM-DDTHH:MM:SSZ）
// 用 strftime（与 database.cpp 的 utcNowIso 一致，避免 snprintf 的 -Wformat-truncation 告警）
std::string utcNowIso() {
    std::time_t now = std::time(nullptr);
    std::tm tm{};
#if defined(_WIN32)
    gmtime_s(&tm, &now);
#else
    gmtime_r(&now, &tm);
#endif
    char buf[32];
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm);
    return std::string(buf);
}

// 手写 JSON 字符串转义，UTF-8 非 ASCII 字节原样透传
void appendJsonEscaped(std::string& out, const std::string& s) {
    static const char* kHex = "0123456789abcdef";
    for (unsigned char c : s) {
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b";  break;
            case '\f': out += "\\f";  break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:
                if (c < 0x20) {
                    out += "\\u00";
                    out.push_back(kHex[(c >> 4) & 0x0F]);
                    out.push_back(kHex[c & 0x0F]);
                } else {
                    out.push_back(static_cast<char>(c));
                }
                break;
        }
    }
}

// 追加 "key":"value" 形式字段（key 与 value 都做 JSON 转义并包引号）。
// first=true 表示这是第一个字段，不加前导逗号。
void appendField(std::string& out, const std::string& key,
                 const std::string& value, bool first) {
    if (!first) out.push_back(',');
    out.push_back('"');
    appendJsonEscaped(out, key);
    out += "\":\"";
    appendJsonEscaped(out, value);
    out.push_back('"');
}

// 实际写出一行日志
void writeLog(Level lv, const std::string& module, const std::string& msg,
              const std::map<std::string, std::string>* fields) {
    std::string line;
    line.reserve(256);
    line.push_back('{');

    appendField(line, "ts", utcNowIso(), true);
    appendField(line, "level", levelToString(lv), false);
    appendField(line, "request_id", t_requestId, false);
    appendField(line, "module", module, false);
    appendField(line, "msg", msg, false);

    if (fields != nullptr) {
        for (const auto& kv : *fields) {
            appendField(line, kv.first, kv.second, false);
        }
    }

    line += "}\n";

    std::lock_guard<std::mutex> lock(g_writeMutex);
    std::fwrite(line.data(), 1, line.size(), stderr);
    std::fflush(stderr);
}

}  // namespace

void setLevelFromEnv() {
    const char* env = std::getenv("DOCSEEK_LOG_LEVEL");
    Level lv = Level::Info;
    if (env != nullptr) {
        std::string s = toLower(std::string(env));
        if (s == "debug") {
            lv = Level::Debug;
        } else if (s == "info") {
            lv = Level::Info;
        } else if (s == "warn") {
            lv = Level::Warn;
        } else if (s == "error") {
            lv = Level::Error;
        } else {
            lv = Level::Info;
        }
    }
    g_level.store(static_cast<int>(lv), std::memory_order_relaxed);
}

Level currentLevel() {
    return static_cast<Level>(g_level.load(std::memory_order_relaxed));
}

std::string newRequestId() {
    unsigned long long n = g_requestCounter.fetch_add(1, std::memory_order_relaxed) + 1;
    char buf[32];
    std::snprintf(buf, sizeof(buf), "r-%06llu", n);
    return std::string(buf);
}

void setRequestId(const std::string& id) {
    t_requestId = id;
}

void clearRequestId() {
    t_requestId.clear();
}

std::string currentRequestId() {
    return t_requestId;
}

void log(Level lv, const std::string& module, const std::string& msg) {
    if (static_cast<int>(lv) < g_level.load(std::memory_order_relaxed)) {
        return;
    }
    writeLog(lv, module, msg, nullptr);
}

void log(Level lv, const std::string& module, const std::string& msg,
         const std::map<std::string, std::string>& fields) {
    if (static_cast<int>(lv) < g_level.load(std::memory_order_relaxed)) {
        return;
    }
    writeLog(lv, module, msg, &fields);
}

}  // namespace docseek
