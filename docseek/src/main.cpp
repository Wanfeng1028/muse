// src/main.cpp —— 文溯 DocSeek 命令行入口
#include "docseek/database.h"
#include "docseek/indexer.h"
#include "docseek/searcher.h"
#include "docseek/service.h"

#include <csignal>
#include <cstdlib>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr const char* kVersion = "0.2.0";

struct GlobalOpts {
    std::string dbPath;
    bool json = false;
};

struct IndexCmdOpts {
    std::vector<std::string> roots;
    std::vector<std::string> exts;
    int64_t maxMb = 5;
};

struct SearchCmdOpts {
    std::string query;
    int limit = 20;
};

struct ServeCmdOpts {
    int port = 8080;
    std::vector<std::string> watchDirs;
    std::vector<std::string> exts;
    int64_t maxMb = 5;
};

// 按优先级解析数据库路径
std::string resolveDbPath(const std::string& cliDb) {
    if (!cliDb.empty()) return cliDb;
    const char* env = std::getenv("DOCSEEK_DB");
    if (env && *env) return std::string(env);
    const char* home = std::getenv("HOME");
    if (home && *home) {
        std::filesystem::path p(home);
        p /= ".local/share/docseek/docseek.db";
        return p.string();
    }
    return "./docseek.db";
}

// 人类可读的字节数
std::string humanBytes(int64_t bytes) {
    if (bytes < 1024) return std::to_string(bytes) + " B";
    double v = static_cast<double>(bytes);
    const char* units[] = {"KB", "MB", "GB"};
    int idx = -1;
    while (v >= 1024.0 && idx < 2) {
        v /= 1024.0;
        ++idx;
    }
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(1) << v << " " << units[idx];
    return oss.str();
}

// JSON 字符串转义
std::string jsonEscape(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 8);
    for (unsigned char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", c);
                    out += buf;
                } else {
                    out += static_cast<char>(c);
                }
        }
    }
    return out;
}

void printUsage() {
    std::cout <<
        "文溯 DocSeek —— 本地全文检索引擎 v" << kVersion << "\n"
        "\n"
        "用法：docseek [--db PATH] [--json] <command> [args]\n"
        "\n"
        "全局选项：\n"
        "  --db PATH        指定数据库文件路径（优先级高于环境变量 DOCSEEK_DB 与默认路径）\n"
        "  --json           以 JSON 格式输出（适用于 search/stats/prune/index）\n"
        "  -h, --help       显示本帮助\n"
        "  -v, --version    显示版本\n"
        "\n"
        "命令：\n"
        "  index <path>... [--ext .txt,.md] [--max-mb N]\n"
        "                   建立或更新索引（可指定多个文件或目录）\n"
        "  search <query...> [--limit N]\n"
        "                   全文搜索，默认返回前 20 条\n"
        "  stats            显示索引统计信息\n"
        "  prune            清理磁盘上已不存在的文件的索引记录\n"
        "  serve [--port N] [--watch DIR]... [--ext .txt,.md] [--max-mb N]\n"
        "                   启动 HTTP 检索服务（默认端口 8080，--port 0 自动分配）；--watch 可重复，指定文件变更实时监控目录\n"
        "  help             显示本帮助\n"
        "  version          显示版本\n"
        "\n"
        "示例：\n"
        "  docseek index ~/notes --ext .md,.txt --max-mb 10\n"
        "  docseek search 全文检索 --limit 5\n"
        "  docseek --json stats\n"
        "  docseek --db /tmp/docseek.db prune\n"
        "  docseek serve --port 8080 --watch ~/notes\n"
        "  docseek --db /data/docseek.db serve --port 0 --watch /data/docs --watch /data/notes\n";
}

// 保证扩展名以 '.' 开头
std::string normalizeExt(const std::string& e) {
    if (e.empty()) return e;
    if (e[0] == '.') return e;
    return "." + e;
}

// 拆分逗号分隔的扩展名
std::vector<std::string> splitExts(const std::string& s) {
    std::vector<std::string> out;
    std::string cur;
    for (char c : s) {
        if (c == ',') {
            if (!cur.empty()) { out.push_back(cur); cur.clear(); }
        } else {
            cur.push_back(c);
        }
    }
    if (!cur.empty()) out.push_back(cur);
    return out;
}

int cmdIndex(docseek::Database& db, const IndexCmdOpts& o, bool json) {
    docseek::IndexOptions opts;
    if (!o.exts.empty()) {
        opts.extensions.clear();
        for (const auto& e : o.exts) opts.extensions.push_back(normalizeExt(e));
    }
    if (o.maxMb > 0) opts.maxFileBytes = o.maxMb * 1024 * 1024;

    docseek::Indexer indexer(db, opts);
    docseek::IndexStats st = indexer.indexPaths(o.roots);

    if (json) {
        std::cout << "{"
                  << "\"scanned\":" << st.scanned << ","
                  << "\"added\":" << st.added << ","
                  << "\"updated\":" << st.updated << ","
                  << "\"unchanged\":" << st.unchanged << ","
                  << "\"removed\":" << st.removed << ","
                  << "\"skipped\":" << st.skipped << ","
                  << "\"errors\":[";
        for (size_t i = 0; i < st.errors.size(); ++i) {
            if (i) std::cout << ",";
            std::cout << "\"" << jsonEscape(st.errors[i]) << "\"";
        }
        std::cout << "]}\n";
    } else {
        std::cout << "索引完成：扫描 " << st.scanned << " 个文件，新增 " << st.added
                  << "，更新 " << st.updated << "，未变 " << st.unchanged
                  << "，清理 " << st.removed << "，跳过 " << st.skipped << "。\n";
        for (const auto& err : st.errors) {
            std::cerr << "  跳过/失败：" << err << "\n";
        }
    }
    return 0;
}

int cmdSearch(docseek::Database& db, const SearchCmdOpts& o, bool json) {
    docseek::Searcher s(db);
    auto hits = s.search(o.query, o.limit);

    if (json) {
        std::cout << "{\"query\":\"" << jsonEscape(o.query) << "\",\"hits\":[";
        for (size_t i = 0; i < hits.size(); ++i) {
            const auto& h = hits[i];
            if (i) std::cout << ",";
            std::cout << "{"
                      << "\"doc_id\":" << h.doc_id << ","
                      << "\"path\":\"" << jsonEscape(h.path) << "\","
                      << "\"title\":\"" << jsonEscape(h.title) << "\","
                      << "\"snippet\":\"" << jsonEscape(h.snippet) << "\","
                      << "\"score\":" << std::fixed << std::setprecision(3) << h.score
                      << "}";
        }
        std::cout << "]}\n";
    } else {
        if (hits.empty()) {
            std::cout << "没有找到匹配 \"" << o.query << "\" 的文档。\n";
        } else {
            for (size_t i = 0; i < hits.size(); ++i) {
                const auto& h = hits[i];
                std::cout << (i + 1) << ". " << h.path << "\n";
                std::cout << "   标题：" << h.title << "\n";
                std::cout << "   评分：" << std::fixed << std::setprecision(3) << h.score << "\n";
                std::cout << "   摘要：" << h.snippet << "\n";
            }
        }
    }
    return 0;
}

int cmdStats(docseek::Database& db, bool json) {
    int64_t docs = db.docCount();
    int64_t total = db.totalBytes();
    int64_t dbf = db.dbFileBytes();

    if (json) {
        std::cout << "{\"documents\":" << docs
                  << ",\"total_bytes\":" << total
                  << ",\"db_bytes\":" << dbf << "}\n";
    } else {
        std::cout << "文档数量：" << docs << "\n";
        std::cout << "内容总大小：" << humanBytes(total) << " (" << total << " 字节)\n";
        std::cout << "数据库文件大小：" << humanBytes(dbf) << " (" << dbf << " 字节)\n";
    }
    return 0;
}

int cmdPrune(docseek::Database& db, bool json) {
    docseek::Indexer indexer(db);
    size_t n = indexer.pruneMissing();
    if (json) {
        std::cout << "{\"removed\":" << n << "}\n";
    } else {
        std::cout << "清理了 " << n << " 条已失效的索引记录。\n";
    }
    return 0;
}

static docseek::Service* g_service = nullptr;

void serveSigHandler(int) {
    if (g_service) g_service->stop();
}

int cmdServe(docseek::Database& db, const ServeCmdOpts& o) {
    docseek::IndexOptions iopts;
    if (!o.exts.empty()) {
        iopts.extensions.clear();
        for (const auto& e : o.exts) iopts.extensions.push_back(normalizeExt(e));
    }
    if (o.maxMb > 0) iopts.maxFileBytes = o.maxMb * 1024 * 1024;

    docseek::ServeOptions sopts;
    sopts.port = o.port;
    sopts.watchDirs = o.watchDirs;
    sopts.indexOpts = iopts;

    docseek::Service svc(db, sopts);
    g_service = &svc;

    std::signal(SIGINT, serveSigHandler);
    std::signal(SIGTERM, serveSigHandler);

    std::cout << "文溯 DocSeek 服务启动，监听端口 "
              << (o.port == 0 ? std::string("自动分配") : std::to_string(o.port))
              << "，按 Ctrl+C 停止。\n";
    svc.run();
    std::cout << "服务已停止。\n";
    g_service = nullptr;
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    GlobalOpts g;
    std::string command;
    IndexCmdOpts indexOpts;
    SearchCmdOpts searchOpts;
    ServeCmdOpts serveOpts;
    std::vector<std::string> searchParts;

    // 参数解析
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--db") {
            if (i + 1 >= argc) {
                std::cerr << "错误：--db 需要参数\n";
                printUsage();
                return 1;
            }
            g.dbPath = argv[++i];
        } else if (a == "--json") {
            g.json = true;
        } else if (a == "--help" || a == "-h") {
            printUsage();
            return 0;
        } else if (a == "--version" || a == "-v") {
            std::cout << "文溯 DocSeek v" << kVersion << "\n";
            return 0;
        } else if (a == "--ext" && (command == "index" || command == "serve")) {
            if (i + 1 >= argc) {
                std::cerr << "错误：--ext 需要参数\n";
                return 1;
            }
            auto parts = splitExts(argv[++i]);
            if (command == "serve") {
                for (auto& p : parts) serveOpts.exts.push_back(p);
            } else {
                for (auto& p : parts) indexOpts.exts.push_back(p);
            }
        } else if (a == "--max-mb" && (command == "index" || command == "serve")) {
            if (i + 1 >= argc) {
                std::cerr << "错误：--max-mb 需要参数\n";
                return 1;
            }
            try {
                if (command == "serve") {
                    serveOpts.maxMb = std::stoll(argv[++i]);
                } else {
                    indexOpts.maxMb = std::stoll(argv[++i]);
                }
            } catch (...) {
                std::cerr << "错误：--max-mb 参数无效\n";
                return 1;
            }
        } else if (a == "--limit" && command == "search") {
            if (i + 1 >= argc) {
                std::cerr << "错误：--limit 需要参数\n";
                return 1;
            }
            try {
                searchOpts.limit = static_cast<int>(std::stoll(argv[++i]));
            } catch (...) {
                std::cerr << "错误：--limit 参数无效\n";
                return 1;
            }
            if (searchOpts.limit <= 0) searchOpts.limit = 20;
        } else if (a == "--port" && command == "serve") {
            if (i + 1 >= argc) {
                std::cerr << "错误：--port 需要参数\n";
                return 1;
            }
            try {
                serveOpts.port = static_cast<int>(std::stoll(argv[++i]));
            } catch (...) {
                std::cerr << "错误：--port 参数无效\n";
                return 1;
            }
            if (serveOpts.port < 0) {
                std::cerr << "错误：--port 参数无效\n";
                return 1;
            }
        } else if (a == "--watch" && command == "serve") {
            if (i + 1 >= argc) {
                std::cerr << "错误：--watch 需要参数\n";
                return 1;
            }
            serveOpts.watchDirs.push_back(argv[++i]);
        } else if (!a.empty() && a[0] == '-' && a != "-") {
            std::cerr << "错误：未知选项 " << a << "\n";
            printUsage();
            return 1;
        } else {
            if (command.empty()) {
                command = a;
            } else if (command == "index") {
                indexOpts.roots.push_back(a);
            } else if (command == "search") {
                searchParts.push_back(a);
            } else {
                std::cerr << "错误：命令 " << command << " 不接受额外参数\n";
                return 1;
            }
        }
    }

    if (command.empty()) {
        std::cerr << "错误：未指定命令\n";
        printUsage();
        return 1;
    }
    if (command == "help") {
        printUsage();
        return 0;
    }
    if (command == "version") {
        std::cout << "文溯 DocSeek v" << kVersion << "\n";
        return 0;
    }

    if (command == "index" && indexOpts.roots.empty()) {
        std::cerr << "错误：index 命令需要至少一个路径\n";
        printUsage();
        return 1;
    }
    if (command == "search") {
        std::ostringstream oss;
        for (size_t i = 0; i < searchParts.size(); ++i) {
            if (i) oss << " ";
            oss << searchParts[i];
        }
        searchOpts.query = oss.str();
        if (searchOpts.query.empty()) {
            std::cerr << "错误：search 命令需要查询字符串\n";
            printUsage();
            return 1;
        }
    }
    if (command != "index" && command != "search" &&
        command != "stats" && command != "prune" && command != "serve") {
        std::cerr << "错误：未知命令 " << command << "\n";
        printUsage();
        return 1;
    }

    try {
        std::string dbPath = resolveDbPath(g.dbPath);
        docseek::Database db = docseek::Database::open(dbPath);

        if (command == "index") return cmdIndex(db, indexOpts, g.json);
        if (command == "search") return cmdSearch(db, searchOpts, g.json);
        if (command == "stats") return cmdStats(db, g.json);
        if (command == "prune") return cmdPrune(db, g.json);
        if (command == "serve") return cmdServe(db, serveOpts);
    } catch (const std::exception& e) {
        std::cerr << "错误：" << e.what() << "\n";
        return 2;
    }
    return 0;
}
