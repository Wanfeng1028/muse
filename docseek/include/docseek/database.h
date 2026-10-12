#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace docseek {

// 文档元数据记录，对应 documents 表中的一行。
struct Document {
    int64_t id = 0;
    std::string path;
    std::string title;
    std::string indexed_at;
    int64_t mtime = 0;
    int64_t size = 0;
};

// 全文检索命中结果，score 越大表示越相关。
struct Hit {
    int64_t doc_id = 0;
    std::string path;
    std::string title;
    std::string snippet;
    double score = 0;
};

// 本地 SQLite 数据库封装，负责文档元数据与 FTS5 索引的读写。
class Database {
public:
    // 打开（不存在则创建）指定路径的数据库并初始化表结构，失败抛 std::runtime_error。
    static Database open(const std::string& path);
    // 析构，释放底层数据库句柄。
    ~Database();
    // 禁用拷贝构造。
    Database(const Database&) = delete;
    // 禁用拷贝赋值。
    Database& operator=(const Database&) = delete;
    // 移动构造，转移底层资源所有权。
    Database(Database&&) noexcept;
    // 移动赋值，转移底层资源所有权。
    Database& operator=(Database&&) noexcept;
    // 按路径插入或更新文档元数据与全文内容，并同步 FTS 行。
    void upsert(const std::string& path, const std::string& title, const std::string& content, int64_t mtime, int64_t size);
    // 按路径删除文档及其 FTS 行，存在则返回 true。
    bool removeByPath(const std::string& path);
    // 返回全部文档元数据，按 id 升序。
    std::vector<Document> list();
    // 按路径查询单个文档元数据，不存在返回 std::nullopt。
    std::optional<Document> findByPath(const std::string& path);
    // 执行 FTS5 匹配查询并返回带片段与评分的命中列表。
    std::vector<Hit> searchFts(const std::string& match_query, int limit);
    // 返回文档总数。
    int64_t docCount();
    // 返回所有文档大小之和（字节）。
    int64_t totalBytes();
    // 返回数据库文件本身占用的字节数。
    int64_t dbFileBytes();

private:
    // 私有实现体，隐藏 SQLite 细节。
    struct Impl;
    std::unique_ptr<Impl> impl_;
    // 私有默认构造，仅供 open() 使用。
    Database();
};

// 返回当前 UTC 时间的 ISO8601 字符串，形如 2026-10-13T06:00:00Z。
std::string utcNowIso();

}  // namespace docseek
