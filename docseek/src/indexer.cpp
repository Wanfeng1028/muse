// src/indexer.cpp
#include "docseek/indexer.h"
#include "docseek/database.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <system_error>
#include <unordered_set>
#include <vector>

namespace fs = std::filesystem;

namespace docseek {

namespace {

// 将字符串转为小写（仅处理 ASCII 范围，路径/扩展名场景足够）
std::string toLowerAscii(const std::string& s) {
    std::string r = s;
    for (char& c : r) {
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    }
    return r;
}

// 将 file_time_type 转换为 Unix 秒级时间戳
int64_t toUnixSeconds(fs::file_time_type ft) {
    using namespace std::chrono;
    auto sctp = time_point_cast<system_clock::duration>(
        ft - fs::file_time_type::clock::now() + system_clock::now());
    return static_cast<int64_t>(system_clock::to_time_t(sctp));
}

// 读取文件前 8KB，用于二进制检测
bool readHead(const std::string& path, std::string& out, size_t maxBytes) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return false;
    out.resize(maxBytes);
    in.read(&out[0], static_cast<std::streamsize>(maxBytes));
    out.resize(static_cast<size_t>(in.gcount()));
    return true;
}

// 读取整个文件内容
bool readAll(const std::string& path, std::string& out) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return false;
    in.seekg(0, std::ios::end);
    std::streamoff sz = in.tellg();
    if (sz < 0) return false;
    in.seekg(0, std::ios::beg);
    out.resize(static_cast<size_t>(sz));
    if (sz > 0) {
        in.read(&out[0], sz);
    }
    return true;
}

// errors 上限
constexpr size_t kMaxErrors = 50;

}  // namespace

Indexer::Indexer(Database& db, IndexOptions opts)
    : db_(db), opts_(std::move(opts)) {}

// 将单个文件加入索引；seen 记录本轮已处理的绝对路径，避免重复
void Indexer::indexOneFile(const std::string& path, IndexStats& st,
                           std::unordered_set<std::string>& seen) {
    try {
        // 计算绝对规范路径
        fs::path p = fs::absolute(path).lexically_normal();
        std::string sp = p.string();
        if (seen.count(sp)) return;
        seen.insert(sp);
        st.scanned++;

        // 扩展名匹配（大小写不敏感）
        std::string ext = toLowerAscii(p.extension().string());
        bool extOk = false;
        for (const auto& e : opts_.extensions) {
            if (toLowerAscii(e) == ext) { extOk = true; break; }
        }
        if (!extOk) { st.skipped++; return; }

        // 文件大小检查
        std::error_code ec;
        auto fsz = fs::file_size(p, ec);
        if (ec) {
            if (st.errors.size() < kMaxErrors) st.errors.push_back(sp + ": " + ec.message());
            st.skipped++;
            return;
        }
        if (static_cast<int64_t>(fsz) > opts_.maxFileBytes) { st.skipped++; return; }

        // 前 8KB 检测二进制
        std::string head;
        if (!readHead(sp, head, 8 * 1024)) {
            if (st.errors.size() < kMaxErrors) st.errors.push_back(sp + ": 无法读取文件");
            st.skipped++;
            return;
        }
        if (head.find('\0') != std::string::npos) { st.skipped++; return; }

        // 读取全文
        std::string content;
        if (!readAll(sp, content)) {
            if (st.errors.size() < kMaxErrors) st.errors.push_back(sp + ": 无法读取文件内容");
            st.skipped++;
            return;
        }

        // mtime 换算
        auto ft = fs::last_write_time(p, ec);
        if (ec) {
            if (st.errors.size() < kMaxErrors) st.errors.push_back(sp + ": " + ec.message());
            st.skipped++;
            return;
        }
        int64_t mtime = toUnixSeconds(ft);
        int64_t size = static_cast<int64_t>(fsz);
        std::string title = p.stem().string();

        // 与已有记录比较
        auto old = db_.findByPath(sp);
        if (old.has_value() && old->mtime == mtime && old->size == size) {
            st.unchanged++;
        } else if (old.has_value()) {
            db_.upsert(sp, title, content, mtime, size);
            st.updated++;
        } else {
            db_.upsert(sp, title, content, mtime, size);
            st.added++;
        }
    } catch (const std::exception& e) {
        if (st.errors.size() < kMaxErrors) {
            st.errors.push_back(path + ": " + e.what());
        }
    }
}

// 批量提交阈值：每处理 N 个文件提交一次批量事务，兼顾速度与 WAL 文件大小。
constexpr size_t kBatchCommitFiles = 500;

// 索引一批 root（文件或目录）
IndexStats Indexer::indexPaths(const std::vector<std::string>& roots) {
    IndexStats st;
    std::unordered_set<std::string> seen;
    size_t batchCount = 0;
    // 每处理一个文件记一次数，达到阈值就提交当前批量事务并开启新的。
    // 注意：indexOneFile 内部已把异常转为 st.errors，只有 db 层致命错误才会抛到这里。
    auto noteFileIndexed = [&]() {
        if (++batchCount >= kBatchCommitFiles) {
            db_.commitBatch();
            db_.beginBatch();
            batchCount = 0;
        }
    };

    db_.beginBatch();
    try {
        for (const auto& root : roots) {
            std::error_code ec;
            if (!fs::exists(root, ec)) {
                if (st.errors.size() < kMaxErrors) {
                    st.errors.push_back(root + ": 路径不存在");
                }
                continue;
            }
            if (fs::is_regular_file(root, ec)) {
                indexOneFile(root, st, seen);
                noteFileIndexed();
                continue;
            }
            if (!fs::is_directory(root, ec)) {
                // 非常规文件/目录（如设备等）直接跳过
                st.skipped++;
                continue;
            }

            // 递归遍历目录
            fs::recursive_directory_iterator it(
                root, fs::directory_options::skip_permission_denied, ec);
            if (ec) {
                if (st.errors.size() < kMaxErrors) {
                    st.errors.push_back(root + ": " + ec.message());
                }
                continue;
            }
            fs::recursive_directory_iterator end;

            while (it != end) {
                try {
                    const fs::directory_entry& entry = *it;

                    // 判断是否为符号链接
                    std::error_code lec;
                    bool isSymlink = fs::is_symlink(entry.symlink_status(lec));

                    if (isSymlink && !opts_.followSymlinks) {
                        // 符号链接且不跟随：跳过，如果是目录则禁止递归
                        if (fs::is_directory(entry.status(lec))) {
                            it.disable_recursion_pending();
                        }
                        it.increment(ec);
                        if (ec) {
                            if (st.errors.size() < kMaxErrors) {
                                st.errors.push_back(root + ": " + ec.message());
                            }
                            break;
                        }
                        continue;
                    }

                    std::error_code sec;
                    fs::file_status status = entry.status(sec);
                    if (sec) {
                        if (st.errors.size() < kMaxErrors) {
                            st.errors.push_back(entry.path().string() + ": " + sec.message());
                        }
                        it.increment(ec);
                        if (ec) break;
                        continue;
                    }

                    if (fs::is_directory(status)) {
                        std::string name = entry.path().filename().string();
                        if (!name.empty() && name[0] == '.') {
                            it.disable_recursion_pending();
                        }
                    } else if (fs::is_regular_file(status)) {
                        indexOneFile(entry.path().string(), st, seen);
                        noteFileIndexed();
                    } else {
                        st.skipped++;
                    }
                } catch (const std::exception& e) {
                    if (st.errors.size() < kMaxErrors) {
                        st.errors.push_back(std::string("遍历异常: ") + e.what());
                    }
                }

                it.increment(ec);
                if (ec) {
                    if (st.errors.size() < kMaxErrors) {
                        st.errors.push_back(root + ": " + ec.message());
                    }
                    break;
                }
            }
        }

        st.removed = pruneMissing();
    } catch (...) {
        db_.abortBatch();
        throw;
    }
    db_.commitBatch();
    return st;
}

// 清理数据库中文件已不存在的记录
size_t Indexer::pruneMissing() {
    size_t n = 0;
    for (const auto& d : db_.list()) {
        std::error_code ec;
        if (!fs::exists(d.path, ec)) {
            if (db_.removeByPath(d.path)) n++;
        }
    }
    return n;
}

}  // namespace docseek
