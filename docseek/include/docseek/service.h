#pragma once

#include <string>
#include <vector>

#include "docseek/indexer.h"

namespace docseek {

class Database;

// 服务运行参数：监听端口、需要实时监控的目录列表、索引选项
struct ServeOptions {
    int port = 8080;                        // HTTP 监听端口，默认 8080
    std::vector<std::string> watchDirs;     // 需要 inotify 实时监控的目录列表
    IndexOptions indexOpts;                 // 索引选项（递归、跳过规则等）
};

// Service：整合 Database、HTTP 服务与文件监控的常驻服务
class Service {
public:
    // 构造服务，watchDirs 中不存在的目录将抛 std::runtime_error
    Service(Database& db, ServeOptions opts);
    // 析构服务，停止 HTTP 与监控并释放资源
    ~Service();
    // 禁止拷贝构造
    Service(const Service&) = delete;
    // 禁止拷贝赋值
    Service& operator=(const Service&) = delete;
    // 注册路由→启动监控→启动 HTTP→阻塞，直到 stop() 被调用
    void run();
    // 请求停止服务，线程安全，可在信号处理或其他线程调用
    void stop();
    // 返回实际监听端口
    int port() const;
    // 返回当前监控的目录列表
    std::vector<std::string> watchedDirs() const;

private:
    class Impl;
    Impl* impl_;
};

}  // namespace docseek
