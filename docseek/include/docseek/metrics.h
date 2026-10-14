#pragma once

#include <cstdint>
#include <deque>
#include <map>
#include <mutex>
#include <string>

namespace docseek {

// 指标采集器：记录查询统计、慢查询与限流拒绝计数。
// 由 Service 持有实例，非单例，全部方法线程安全。
class Metrics {
public:
    explicit Metrics(double slowThresholdMs = 500.0);

    // 记录一次查询：endpoint（如 "search"/"locate"）、查询词、耗时（毫秒）
    void recordQuery(const std::string& endpoint, const std::string& query,
                     double latencyMs);

    // 记录一次 locate 限流拒绝
    void recordLocateRejected();

    // 序列化为 JSON，uptimeSec 由调用方（Service）传入
    std::string toJson(uint64_t uptimeSec) const;

private:
    struct EndpointStat {
        uint64_t count = 0;
        double sumMs = 0.0;
        double maxMs = 0.0;
    };

    struct SlowQuery {
        std::string ts;
        std::string endpoint;
        std::string query;
        double latencyMs = 0.0;
    };

    double slowThresholdMs_;
    EndpointStat search_;
    EndpointStat locate_;
    uint64_t locateRejected_ = 0;
    // Top 查询词计数表
    std::map<std::string, uint64_t> topQueries_;
    // 最近慢查询，最多保留 20 条
    std::deque<SlowQuery> slowQueries_;

    mutable std::mutex mutex_;
};

}  // namespace docseek
