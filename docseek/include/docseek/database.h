#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace docseek {

// 未显式指定用户时的默认归属用户。
inline constexpr const char* kDefaultUser = "local";

// 校验用户名：长度 1~64，不含控制字符（字节 <0x20 或 ==0x7f），非法抛 std::runtime_error。
void checkUserValid(const std::string& user);

// 文档元数据记录，对应 documents 表中的一行。
struct Document {
    int64_t id = 0;
    std::string path;
    std::string title;
    std::string indexed_at;
    int64_t mtime = 0;
    int64_t size = 0;
    std::string user; // 索引归属用户
};

// 全文检索命中结果，score 越大表示越相关。
struct Hit {
    int64_t doc_id = 0;
    std::string path;
    std::string title;
    std::string snippet;
    double score = 0;
    std::string file_type;  // 文件类型标签：PDF/HTML/MD/TXT，未知为空
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
    // user 指定归属用户，默认 kDefaultUser。
    void upsert(const std::string& path, const std::string& title, const std::string& content, int64_t mtime, int64_t size, const std::string& user = kDefaultUser);
    // 按路径删除文档及其 FTS 行，存在则返回 true。
    // user 指定归属用户，默认 kDefaultUser。
    bool removeByPath(const std::string& path, const std::string& user = kDefaultUser);
    // 删除该用户全部文档（含 FTS 行），返回删除条数；用户不存在返回 0，不抛异常。
    size_t removeByUser(const std::string& user);
    // 批量事务：beginBatch() 后，upsert/removeByPath 不再各自开事务，
    // 由调用方统一 commitBatch() 提交；abortBatch() 回滚。
    // 已在批量事务中再次 beginBatch() 抛 std::runtime_error；
    // 未在批量事务中 commitBatch() 抛 std::runtime_error；
    // abortBatch() 在未开事务时为空操作（避免掩盖调用方的原始异常）。
    void beginBatch();
    void commitBatch();
    void abortBatch();
    // 当前是否处于批量事务中。
    bool inBatch() const;
    // 返回 open() 时传入的数据库文件路径。
    std::string path() const;
    // 在线备份：用 SQLite backup API 把 srcPath 的库完整复制到 dstPath。
    // dst 父目录不存在时自动创建；失败抛 std::runtime_error；不锁源库写入。
    static void backup(const std::string& srcPath, const std::string& dstPath);
    // 校验 path 是否为有效的文溯数据库：只读打开，检查 user_version
    // 在 [1, 当前 schema 版本] 内且 documents 表存在。任何异常返回 false，不抛。
    static bool isValidDocseekDb(const std::string& path);
    // 返回指定用户的全部文档元数据，按 id 升序。user 默认 kDefaultUser。
    std::vector<Document> list(const std::string& user = kDefaultUser);
    // 按路径查询单个文档元数据，不存在返回 std::nullopt。user 默认 kDefaultUser。
    std::optional<Document> findByPath(const std::string& path, const std::string& user = kDefaultUser);
    // 执行 FTS5 匹配查询并返回带片段与评分的命中列表。user 默认 kDefaultUser。
    std::vector<Hit> searchFts(const std::string& match_query, int limit, const std::string& user = kDefaultUser);
    // 返回指定用户的文档总数。user 默认 kDefaultUser。
    int64_t docCount(const std::string& user = kDefaultUser);
    // 返回该用户文档中出现过该词的文档数（FTS5 MATCH 查询，走 jieba 分词；term 为空返回 0）。
    int64_t docFrequency(const std::string& term, const std::string& user = kDefaultUser);
    // 按文档 id 取 FTS 全文 content；不存在返回 std::nullopt。
    std::optional<std::string> getContentById(int64_t doc_id);
    // 返回指定用户所有文档大小之和（字节）。user 默认 kDefaultUser。
    int64_t totalBytes(const std::string& user = kDefaultUser);
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
