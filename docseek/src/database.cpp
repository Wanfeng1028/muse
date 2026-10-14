// src/database.cpp
#include "docseek/database.h"

#include "docseek/jieba_tokenizer.h"

#include <sqlite3.h>

#include <chrono>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace docseek {

namespace {

// 简单的 SQL 执行封装，出错抛 runtime_error
void execSql(sqlite3* db, const char* sql) {
    char* errmsg = nullptr;
    int rc = sqlite3_exec(db, sql, nullptr, nullptr, &errmsg);
    if (rc != SQLITE_OK) {
        std::string msg = errmsg ? errmsg : "unknown error";
        if (errmsg) sqlite3_free(errmsg);
        throw std::runtime_error("sqlite exec failed: " + msg);
    }
}

// Stmt RAII 封装
class Stmt {
public:
    Stmt(sqlite3* db, const char* sql) : db_(db) {
        int rc = sqlite3_prepare_v2(db_, sql, -1, &stmt_, nullptr);
        if (rc != SQLITE_OK) {
            throw std::runtime_error(std::string("sqlite prepare failed: ") +
                                     sqlite3_errmsg(db_));
        }
    }
    ~Stmt() {
        if (stmt_) sqlite3_finalize(stmt_);
    }
    Stmt(const Stmt&) = delete;
    Stmt& operator=(const Stmt&) = delete;

    void bindText(int idx, const std::string& v) {
        int rc = sqlite3_bind_text(stmt_, idx, v.c_str(),
                                   static_cast<int>(v.size()), SQLITE_TRANSIENT);
        if (rc != SQLITE_OK) {
            throw std::runtime_error(std::string("sqlite bind text failed: ") +
                                     sqlite3_errmsg(db_));
        }
    }
    void bindInt64(int idx, int64_t v) {
        int rc = sqlite3_bind_int64(stmt_, idx, v);
        if (rc != SQLITE_OK) {
            throw std::runtime_error(std::string("sqlite bind int64 failed: ") +
                                     sqlite3_errmsg(db_));
        }
    }
    // 返回 true 表示有一行；false 表示结束
    bool step() {
        int rc = sqlite3_step(stmt_);
        if (rc == SQLITE_ROW) return true;
        if (rc == SQLITE_DONE) return false;
        throw std::runtime_error(std::string("sqlite step failed: ") +
                                 sqlite3_errmsg(db_));
    }
    void exec() {
        int rc = sqlite3_step(stmt_);
        if (rc != SQLITE_DONE) {
            throw std::runtime_error(std::string("sqlite step failed: ") +
                                     sqlite3_errmsg(db_));
        }
    }

    int64_t columnInt64(int idx) { return sqlite3_column_int64(stmt_, idx); }

    double columnDouble(int idx) { return sqlite3_column_double(stmt_, idx); }

    std::string columnText(int idx) {
        const unsigned char* p = sqlite3_column_text(stmt_, idx);
        if (!p) return std::string();
        int n = sqlite3_column_bytes(stmt_, idx);
        return std::string(reinterpret_cast<const char*>(p), static_cast<size_t>(n));
    }

    bool columnIsNull(int idx) {
        return sqlite3_column_type(stmt_, idx) == SQLITE_NULL;
    }

private:
    sqlite3* db_ = nullptr;
    sqlite3_stmt* stmt_ = nullptr;
};

}  // namespace

std::string utcNowIso() {
    using namespace std::chrono;
    auto now = system_clock::now();
    std::time_t t = system_clock::to_time_t(now);
    std::tm tm_utc{};
#if defined(_WIN32)
    gmtime_s(&tm_utc, &t);
#else
    gmtime_r(&t, &tm_utc);
#endif
    char buf[32];
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm_utc);
    return std::string(buf);
}

struct Database::Impl {
    sqlite3* db = nullptr;
    std::string path;
    bool inBatch = false;  // true 表示调用方已 beginBatch，upsert/removeByPath 不再自行开事务
};

// 当前 schema 版本：3 = FTS5 使用 jieba 中文分词器；<3 为 unicode61 旧库。
constexpr int kSchemaVersion = 3;

namespace {

// 读取 PRAGMA user_version（出错返回 0，视为最旧版本）。
int readUserVersion(sqlite3* db) {
    sqlite3_stmt* stmt = nullptr;
    int v = 0;
    if (sqlite3_prepare_v2(db, "PRAGMA user_version;", -1, &stmt, nullptr) ==
        SQLITE_OK) {
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            v = sqlite3_column_int(stmt, 0);
        }
        sqlite3_finalize(stmt);
    }
    return v;
}

// 写入 PRAGMA user_version。
void writeUserVersion(sqlite3* db, int v) {
    std::string sql = "PRAGMA user_version = " + std::to_string(v) + ";";
    execSql(db, sql.c_str());
}

// 判断表是否存在。
bool tableExists(sqlite3* db, const char* name) {
    sqlite3_stmt* stmt = nullptr;
    bool exists = false;
    const char* sql =
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;";
    if (sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, name, -1, SQLITE_TRANSIENT);
        exists = (sqlite3_step(stmt) == SQLITE_ROW);
        sqlite3_finalize(stmt);
    }
    return exists;
}

// 旧库迁移：把 unicode61 分词的 documents_fts 重建为 jieba 分词。
// FTS5 默认 contentful，title/content 可直接读出；事务包裹，失败回滚。
void migrateFtsToJieba(sqlite3* db) {
    struct Row {
        int64_t rowid;
        std::string title;
        std::string content;
    };
    std::vector<Row> rows;
    {
        sqlite3_stmt* stmt = nullptr;
        const char* sql = "SELECT rowid, title, content FROM documents_fts;";
        if (sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr) != SQLITE_OK) {
            throw std::runtime_error(std::string("迁移读取旧 FTS 表失败: ") +
                                     sqlite3_errmsg(db));
        }
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            Row r;
            r.rowid = sqlite3_column_int64(stmt, 0);
            const unsigned char* t = sqlite3_column_text(stmt, 1);
            const unsigned char* c = sqlite3_column_text(stmt, 2);
            r.title = t ? reinterpret_cast<const char*>(t) : "";
            r.content = c ? reinterpret_cast<const char*>(c) : "";
            rows.push_back(std::move(r));
        }
        sqlite3_finalize(stmt);
    }

    execSql(db, "BEGIN IMMEDIATE;");
    try {
        execSql(db, "DROP TABLE documents_fts;");
        execSql(db,
                "CREATE VIRTUAL TABLE documents_fts USING fts5("
                "title, content, tokenize='jieba');");
        sqlite3_stmt* ins = nullptr;
        const char* sql =
            "INSERT INTO documents_fts(rowid, title, content) VALUES(?,?,?);";
        if (sqlite3_prepare_v2(db, sql, -1, &ins, nullptr) != SQLITE_OK) {
            throw std::runtime_error(std::string("迁移准备插入失败: ") +
                                     sqlite3_errmsg(db));
        }
        for (const Row& r : rows) {
            sqlite3_bind_int64(ins, 1, r.rowid);
            sqlite3_bind_text(ins, 2, r.title.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(ins, 3, r.content.c_str(), -1, SQLITE_TRANSIENT);
            if (sqlite3_step(ins) != SQLITE_DONE) {
                std::string e = sqlite3_errmsg(db);
                sqlite3_finalize(ins);
                throw std::runtime_error("迁移插入失败: " + e);
            }
            sqlite3_reset(ins);
            sqlite3_clear_bindings(ins);
        }
        sqlite3_finalize(ins);
        execSql(db, "COMMIT;");
    } catch (...) {
        execSql(db, "ROLLBACK;");
        throw;
    }
}

}  // namespace

Database::Database() : impl_(std::make_unique<Impl>()) {}

Database Database::open(const std::string& path) {
    Database d;
    d.impl_->path = path;

    // 若路径中包含目录，确保父目录存在（":memory:" 等特殊情况跳过）
    if (path != ":memory:") {
        std::filesystem::path p(path);
        std::filesystem::path parent = p.parent_path();
        if (!parent.empty()) {
            std::error_code ec;
            std::filesystem::create_directories(parent, ec);
            if (ec) {
                throw std::runtime_error("无法创建数据库目录: " + parent.string() +
                                         " (" + ec.message() + ")");
            }
        }
    }

    sqlite3* db = nullptr;
    int rc = sqlite3_open(path.c_str(), &db);
    if (rc != SQLITE_OK) {
        std::string msg = db ? sqlite3_errmsg(db) : "unknown error";
        if (db) sqlite3_close(db);
        throw std::runtime_error("无法打开数据库: " + msg);
    }
    d.impl_->db = db;

    // 注册 jieba 中文分词器（FTS5 自定义 tokenizer）。词典缺失时直接失败，
    // 避免静默建出错误的索引。
    if (registerJiebaTokenizer(db) != SQLITE_OK) {
        std::string msg = "FTS5 jieba 分词器注册失败（词典缺失？请检查 DOCSEEK_DICT_DIR）";
        sqlite3_close(db);
        d.impl_->db = nullptr;
        throw std::runtime_error(msg);
    }

    try {
        execSql(db, "PRAGMA journal_mode=WAL;");
        execSql(db, "PRAGMA foreign_keys=ON;");
        execSql(db,
                "CREATE TABLE IF NOT EXISTS documents("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "path TEXT NOT NULL UNIQUE,"
                "title TEXT NOT NULL,"
                "mtime INTEGER NOT NULL,"
                "size INTEGER NOT NULL,"
                "indexed_at TEXT NOT NULL);");
        // schema 版本：3 = jieba 分词器时代；<3 为 unicode61 旧库，需迁移。
        int uv = readUserVersion(db);
        if (uv > kSchemaVersion) {
            throw std::runtime_error("数据库版本过新（user_version=" +
                                     std::to_string(uv) + "），请升级 docseek");
        }
        bool ftsExists = tableExists(db, "documents_fts");
        if (!ftsExists) {
            execSql(db,
                    "CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5("
                    "title, content, tokenize='jieba');");
            writeUserVersion(db, kSchemaVersion);
        } else if (uv < kSchemaVersion) {
            migrateFtsToJieba(db);
            writeUserVersion(db, kSchemaVersion);
        }
    } catch (...) {
        sqlite3_close(db);
        d.impl_->db = nullptr;
        throw;
    }

    return d;
}

Database::~Database() {
    if (impl_ && impl_->db) {
        sqlite3_close(impl_->db);
        impl_->db = nullptr;
    }
}

Database::Database(Database&& other) noexcept : impl_(std::move(other.impl_)) {
    if (!impl_) impl_ = std::make_unique<Impl>();
}

Database& Database::operator=(Database&& other) noexcept {
    if (this != &other) {
        if (impl_ && impl_->db) {
            sqlite3_close(impl_->db);
            impl_->db = nullptr;
        }
        impl_ = std::move(other.impl_);
        if (!impl_) impl_ = std::make_unique<Impl>();
    }
    return *this;
}

void Database::upsert(const std::string& path, const std::string& title,
                      const std::string& content, int64_t mtime, int64_t size) {
    sqlite3* db = impl_->db;
    if (!db) throw std::runtime_error("database 未打开");

    // 批量事务内由调用方统一提交，此处不许嵌套 BEGIN。
    bool outer = impl_->inBatch;
    if (!outer) execSql(db, "BEGIN IMMEDIATE;");
    try {
        int64_t id = 0;
        bool exists = false;
        {
            Stmt s(db, "SELECT id FROM documents WHERE path=?;");
            s.bindText(1, path);
            if (s.step()) {
                id = s.columnInt64(0);
                exists = true;
            }
        }

        std::string now = utcNowIso();
        if (exists) {
            Stmt s(db,
                   "UPDATE documents SET title=?, mtime=?, size=?, indexed_at=? "
                   "WHERE id=?;");
            s.bindText(1, title);
            s.bindInt64(2, mtime);
            s.bindInt64(3, size);
            s.bindText(4, now);
            s.bindInt64(5, id);
            s.exec();
        } else {
            Stmt s(db,
                   "INSERT INTO documents(path, title, mtime, size, indexed_at) "
                   "VALUES(?,?,?,?,?);");
            s.bindText(1, path);
            s.bindText(2, title);
            s.bindInt64(3, mtime);
            s.bindInt64(4, size);
            s.bindText(5, now);
            s.exec();
            id = sqlite3_last_insert_rowid(db);
        }

        // 先删后插，同步 rowid
        {
            Stmt s(db, "DELETE FROM documents_fts WHERE rowid=?;");
            s.bindInt64(1, id);
            s.exec();
        }
        {
            Stmt s(db,
                   "INSERT INTO documents_fts(rowid, title, content) VALUES(?,?,?);");
            s.bindInt64(1, id);
            s.bindText(2, title);
            s.bindText(3, content);
            s.exec();
        }

        if (!outer) execSql(db, "COMMIT;");
    } catch (...) {
        if (!outer) {
            try {
                execSql(db, "ROLLBACK;");
            } catch (...) {
            }
        }
        throw;
    }
}

bool Database::removeByPath(const std::string& path) {
    sqlite3* db = impl_->db;
    if (!db) throw std::runtime_error("database 未打开");

    bool outer = impl_->inBatch;
    if (!outer) execSql(db, "BEGIN IMMEDIATE;");
    try {
        int64_t id = 0;
        bool exists = false;
        {
            Stmt s(db, "SELECT id FROM documents WHERE path=?;");
            s.bindText(1, path);
            if (s.step()) {
                id = s.columnInt64(0);
                exists = true;
            }
        }
        if (!exists) {
            if (!outer) execSql(db, "COMMIT;");
            return false;
        }
        {
            Stmt s(db, "DELETE FROM documents_fts WHERE rowid=?;");
            s.bindInt64(1, id);
            s.exec();
        }
        {
            Stmt s(db, "DELETE FROM documents WHERE id=?;");
            s.bindInt64(1, id);
            s.exec();
        }
        if (!outer) execSql(db, "COMMIT;");
        return true;
    } catch (...) {
        if (!outer) {
            try {
                execSql(db, "ROLLBACK;");
            } catch (...) {
            }
        }
        throw;
    }
}

void Database::beginBatch() {
    sqlite3* db = impl_->db;
    if (!db) throw std::runtime_error("database 未打开");
    if (impl_->inBatch) throw std::runtime_error("批量事务已开启，不许嵌套 beginBatch");
    execSql(db, "BEGIN IMMEDIATE;");
    impl_->inBatch = true;
}

void Database::commitBatch() {
    sqlite3* db = impl_->db;
    if (!db) throw std::runtime_error("database 未打开");
    if (!impl_->inBatch) throw std::runtime_error("未开启批量事务，不许 commitBatch");
    try {
        execSql(db, "COMMIT;");
        impl_->inBatch = false;
    } catch (...) {
        try {
            execSql(db, "ROLLBACK;");
        } catch (...) {
        }
        impl_->inBatch = false;
        throw;
    }
}

void Database::abortBatch() {
    sqlite3* db = impl_->db;
    if (!db || !impl_->inBatch) return;  // 空操作：避免掩盖调用方的原始异常
    try {
        execSql(db, "ROLLBACK;");
    } catch (...) {
    }
    impl_->inBatch = false;
}

bool Database::inBatch() const {
    return impl_ && impl_->inBatch;
}

std::string Database::path() const {
    return impl_ ? impl_->path : std::string();
}

void Database::backup(const std::string& srcPath, const std::string& dstPath) {
    // 目标父目录自动创建
    if (dstPath != ":memory:") {
        std::filesystem::path p(dstPath);
        std::filesystem::path parent = p.parent_path();
        if (!parent.empty()) {
            std::error_code ec;
            std::filesystem::create_directories(parent, ec);
            if (ec) {
                throw std::runtime_error("无法创建备份目录: " + parent.string() +
                                         " (" + ec.message() + ")");
            }
        }
    }
    sqlite3* src = nullptr;
    sqlite3* dst = nullptr;
    // 先打开源（只读），再打开目标，任一失败都要关闭已打开的句柄
    if (sqlite3_open_v2(srcPath.c_str(), &src, SQLITE_OPEN_READONLY, nullptr) != SQLITE_OK) {
        std::string msg = src ? sqlite3_errmsg(src) : "unknown error";
        if (src) sqlite3_close(src);
        throw std::runtime_error("备份：无法只读打开源数据库: " + msg);
    }
    if (sqlite3_open(dstPath.c_str(), &dst) != SQLITE_OK) {
        std::string msg = dst ? sqlite3_errmsg(dst) : "unknown error";
        if (dst) sqlite3_close(dst);
        sqlite3_close(src);
        throw std::runtime_error("备份：无法打开目标文件: " + msg);
    }
    sqlite3_backup* b = sqlite3_backup_init(dst, "main", src, "main");
    if (!b) {
        std::string msg = sqlite3_errmsg(dst);
        sqlite3_close(dst);
        sqlite3_close(src);
        throw std::runtime_error("备份初始化失败: " + msg);
    }
    int rc = sqlite3_backup_step(b, -1);
    sqlite3_backup_finish(b);
    sqlite3_close(dst);
    sqlite3_close(src);
    if (rc != SQLITE_DONE) {
        throw std::runtime_error("备份复制失败（rc=" + std::to_string(rc) + "）");
    }
}

bool Database::isValidDocseekDb(const std::string& path) {
    sqlite3* db = nullptr;
    if (sqlite3_open_v2(path.c_str(), &db, SQLITE_OPEN_READONLY, nullptr) != SQLITE_OK) {
        if (db) sqlite3_close(db);
        return false;
    }
    bool ok = false;
    sqlite3_stmt* st = nullptr;
    int uv = -1;
    if (sqlite3_prepare_v2(db, "PRAGMA user_version;", -1, &st, nullptr) == SQLITE_OK) {
        if (sqlite3_step(st) == SQLITE_ROW) uv = sqlite3_column_int(st, 0);
        sqlite3_finalize(st);
        st = nullptr;
    }
    // kSchemaVersion 在本文件匿名命名空间内定义（当前为 3）
    if (uv >= 1 && uv <= kSchemaVersion) {
        const char* sql =
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents' LIMIT 1;";
        if (sqlite3_prepare_v2(db, sql, -1, &st, nullptr) == SQLITE_OK) {
            ok = (sqlite3_step(st) == SQLITE_ROW);
            sqlite3_finalize(st);
        }
    }
    sqlite3_close(db);
    return ok;
}

std::vector<Document> Database::list() {
    sqlite3* db = impl_->db;
    if (!db) throw std::runtime_error("database 未打开");

    std::vector<Document> out;
    Stmt s(db,
           "SELECT id,path,title,mtime,size,indexed_at FROM documents ORDER BY id;");
    while (s.step()) {
        Document d;
        d.id = s.columnInt64(0);
        d.path = s.columnText(1);
        d.title = s.columnText(2);
        d.mtime = s.columnInt64(3);
        d.size = s.columnInt64(4);
        d.indexed_at = s.columnText(5);
        out.push_back(std::move(d));
    }
    return out;
}

std::optional<Document> Database::findByPath(const std::string& path) {
    sqlite3* db = impl_->db;
    if (!db) throw std::runtime_error("database 未打开");

    Stmt s(db,
           "SELECT id,path,title,mtime,size,indexed_at FROM documents WHERE path=?;");
    s.bindText(1, path);
    if (!s.step()) return std::nullopt;
    Document d;
    d.id = s.columnInt64(0);
    d.path = s.columnText(1);
    d.title = s.columnText(2);
    d.mtime = s.columnInt64(3);
    d.size = s.columnInt64(4);
    d.indexed_at = s.columnText(5);
    return d;
}

std::vector<Hit> Database::searchFts(const std::string& match_query, int limit) {
    std::vector<Hit> out;
    if (match_query.empty()) return out;

    sqlite3* db = impl_->db;
    if (!db) throw std::runtime_error("database 未打开");

    int effLimit = limit <= 0 ? 20 : limit;

    Stmt s(db,
           "SELECT d.id, d.path, d.title, "
           "snippet(documents_fts, 1, '', '', '…', 30), "
           "-bm25(documents_fts) "
           "FROM documents_fts JOIN documents d ON d.id = documents_fts.rowid "
           "WHERE documents_fts MATCH ? ORDER BY 5 DESC LIMIT ?;");
    s.bindText(1, match_query);
    s.bindInt64(2, effLimit);

    while (s.step()) {
        Hit h;
        h.doc_id = s.columnInt64(0);
        h.path = s.columnText(1);
        h.title = s.columnText(2);
        h.snippet = s.columnIsNull(3) ? std::string() : s.columnText(3);
        h.score = s.columnDouble(4);
        out.push_back(std::move(h));
    }
    return out;
}

int64_t Database::docCount() {
    sqlite3* db = impl_->db;
    if (!db) throw std::runtime_error("database 未打开");
    Stmt s(db, "SELECT COUNT(*) FROM documents;");
    if (s.step()) return s.columnInt64(0);
    return 0;
}

std::optional<std::string> Database::getContentById(int64_t doc_id) {
    sqlite3* db = impl_->db;
    if (!db) throw std::runtime_error("database 未打开");
    Stmt s(db, "SELECT content FROM documents_fts WHERE rowid=?;");
    s.bindInt64(1, doc_id);
    if (s.step()) {
        if (s.columnIsNull(0)) return std::nullopt;
        return s.columnText(0);
    }
    return std::nullopt;
}

int64_t Database::totalBytes() {
    sqlite3* db = impl_->db;
    if (!db) throw std::runtime_error("database 未打开");
    Stmt s(db, "SELECT COALESCE(SUM(size),0) FROM documents;");
    if (s.step()) return s.columnInt64(0);
    return 0;
}

int64_t Database::dbFileBytes() {
    sqlite3* db = impl_->db;
    if (!db) throw std::runtime_error("database 未打开");
    Stmt s(db, "PRAGMA database_list;");
    std::string file;
    while (s.step()) {
        // 列：seq, name, file
        std::string name = s.columnText(1);
        if (name == "main") {
            file = s.columnText(2);
            break;
        }
    }
    if (file.empty()) return -1;
    std::error_code ec;
    auto sz = std::filesystem::file_size(file, ec);
    if (ec) return -1;
    return static_cast<int64_t>(sz);
}

}  // namespace docseek
