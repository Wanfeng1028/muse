#include "docseek/metrics.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <ctime>
#include <deque>
#include <map>
#include <mutex>
#include <string>
#include <vector>

namespace docseek {
namespace {

// 去除字符串首尾空白（ASCII 空白）
std::string trim(const std::string& s) {
    size_t begin = 0;
    size_t end = s.size();
    while (begin < end && std::isspace(static_cast<unsigned char>(s[begin]))) {
        ++begin;
    }
    while (end > begin && std::isspace(static_cast<unsigned char>(s[end - 1]))) {
        --end;
    }
    return s.substr(begin, end - begin);
}

// 手写 JSON 字符串转义
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

// 返回当前 UTC 时间的 ISO8601 字符串
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

// 输出保留 1 位小数的浮点数
std::string formatOneDecimal(double v) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.1f", v);
    return std::string(buf);
}

}  // namespace

Metrics::Metrics(double slowThresholdMs) : slowThresholdMs_(slowThresholdMs) {}

void Metrics::recordQuery(const std::string& endpoint, const std::string& query,
                          double latencyMs) {
    std::lock_guard<std::mutex> lock(mutex_);

    EndpointStat* stat = nullptr;
    if (endpoint == "search") {
        stat = &search_;
    } else if (endpoint == "locate") {
        stat = &locate_;
    }
    if (stat != nullptr) {
        stat->count += 1;
        stat->sumMs += latencyMs;
        if (latencyMs > stat->maxMs) {
            stat->maxMs = latencyMs;
        }
    }

    std::string trimmed = trim(query);
    if (!trimmed.empty()) {
        topQueries_[trimmed] += 1;
    }

    if (latencyMs >= slowThresholdMs_) {
        SlowQuery sq;
        sq.ts = utcNowIso();
        sq.endpoint = endpoint;
        sq.query = trimmed;
        sq.latencyMs = latencyMs;
        slowQueries_.push_back(std::move(sq));
        while (slowQueries_.size() > 20) {
            slowQueries_.pop_front();
        }
    }
}

void Metrics::recordLocateRejected() {
    std::lock_guard<std::mutex> lock(mutex_);
    locateRejected_ += 1;
}

std::string Metrics::toJson(uint64_t uptimeSec) const {
    std::lock_guard<std::mutex> lock(mutex_);

    std::string out;
    out.reserve(512);
    out.push_back('{');

    // uptime_sec
    out += "\"uptime_sec\":";
    out += std::to_string(uptimeSec);

    // queries
    out += ",\"queries\":{";

    out += "\"search\":{";
    out += "\"count\":";
    out += std::to_string(search_.count);
    out += ",\"avg_ms\":";
    {
        double avg = search_.count > 0
                         ? search_.sumMs / static_cast<double>(search_.count)
                         : 0.0;
        out += formatOneDecimal(avg);
    }
    out += ",\"max_ms\":";
    out += formatOneDecimal(search_.maxMs);
    out.push_back('}');

    out += ",\"locate\":{";
    out += "\"count\":";
    out += std::to_string(locate_.count);
    out += ",\"avg_ms\":";
    {
        double avg = locate_.count > 0
                         ? locate_.sumMs / static_cast<double>(locate_.count)
                         : 0.0;
        out += formatOneDecimal(avg);
    }
    out += ",\"max_ms\":";
    out += formatOneDecimal(locate_.maxMs);
    out.push_back('}');

    out.push_back('}');  // end queries

    // top_queries：按计数降序取前 10
    std::vector<std::pair<std::string, uint64_t>> topVec(topQueries_.begin(),
                                                         topQueries_.end());
    std::sort(topVec.begin(), topVec.end(),
              [](const std::pair<std::string, uint64_t>& a,
                 const std::pair<std::string, uint64_t>& b) {
                  if (a.second != b.second) {
                      return a.second > b.second;
                  }
                  return a.first < b.first;
              });
    if (topVec.size() > 10) {
        topVec.resize(10);
    }

    out += ",\"top_queries\":[";
    for (size_t i = 0; i < topVec.size(); ++i) {
        if (i > 0) {
            out.push_back(',');
        }
        out += "{\"q\":\"";
        appendJsonEscaped(out, topVec[i].first);
        out += "\",\"count\":";
        out += std::to_string(topVec[i].second);
        out.push_back('}');
    }
    out.push_back(']');

    // slow_queries
    out += ",\"slow_queries\":[";
    for (size_t i = 0; i < slowQueries_.size(); ++i) {
        const SlowQuery& sq = slowQueries_[i];
        if (i > 0) {
            out.push_back(',');
        }
        out += "{\"ts\":\"";
        appendJsonEscaped(out, sq.ts);
        out += "\",\"endpoint\":\"";
        appendJsonEscaped(out, sq.endpoint);
        out += "\",\"q\":\"";
        appendJsonEscaped(out, sq.query);
        out += "\",\"latency_ms\":";
        out += formatOneDecimal(sq.latencyMs);
        out.push_back('}');
    }
    out.push_back(']');

    // locate_rejected
    out += ",\"locate_rejected\":";
    out += std::to_string(locateRejected_);

    out.push_back('}');
    return out;
}

}  // namespace docseek
