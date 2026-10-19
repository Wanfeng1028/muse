// src/main.cpp —— 文溯 DocSeek 命令行入口
#include "docseek/database.h"
#include "docseek/indexer.h"
#include "docseek/locator.h"
#include "docseek/query_parser.h"
#include "docseek/searcher.h"
#include "docseek/service.h"
#include "docseek/version.h"


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
#include <cmath>

#include <string>
#include <algorithm>
#include <vector>
#if defined(__linux__)
#include <unistd.h>  // isatty
#endif

namespace {

// 唯一来源：docseek::kDocseekVersion（include/docseek/version.h），发版只改那一处。
constexpr const char* kVersion = docseek::kDocseekVersion;


struct GlobalOpts {
    std::string dbPath;
    bool json = false;
};

struct IndexCmdOpts {
    std::vector<std::string> roots;
    std::vector<std::string> exts;
    int64_t maxMb = 5;
};

double readWeightEnv(const char* name, double def) {
    const char* raw = std::getenv(name);
    if (raw == nullptr || *raw == '\0') return def;
    char* end = nullptr;
    double v = std::strtod(raw, &end);
    if (end == raw || *end != '\0' || !std::isfinite(v)) {
        std::cerr << "警告：" << name << " 参数无效，使用默认值 " << def << "\n";
        return def;
    }
    return v;
}

struct SearchCmdOpts {
    std::string query;
    int limit = 20;
    double titleBoost = readWeightEnv("DOCSEEK_TITLE_BOOST", 1.0);
    double phraseBoost = readWeightEnv("DOCSEEK_PHRASE_BOOST", 2.0);
    bool explain = false;
};


struct LocateCmdOpts {
    std::string query;
    int limit = 5;
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
        "  --json           以 JSON 格式输出（适用于 search/stats/prune/index/backup/restore）\n"
        "  -h, --help       显示本帮助\n"
        "  -v, --version    显示版本\n"
        "\n"
        "命令：\n"
        "  index <path>... [--ext .txt,.md] [--max-mb N]\n"
        "                   建立或更新索引（可指定多个文件或目录）\n"
        "  search <query...> [--limit N] [--title-boost F] [--phrase-boost F] [--explain]\n"
        "                   全文搜索，默认返回前 20 条\n"
        "                   --title-boost/--phrase-boost 设置权重（默认 1.0/2.0）\n"
        "                   --explain 输出每条命中的评分分量明细\n"

        "  locate <query...> [--limit N]\n"
        "                   自然语言定位原文：问句直达文件:行号，默认返回前 5 段\n"
        "  stats            显示索引统计信息\n"
        "  prune            清理磁盘上已不存在的文件的索引记录\n"
        "  backup <dest>    在线备份数据库到 dest（SQLite backup API，备份时不阻塞写入）\n"
        "  restore <src>    用备份文件 src 原子替换当前数据库（先校验有效性再替换）\n"
        "  serve [--port N] [--watch DIR]... [--ext .txt,.md] [--max-mb N]\n"
        "                   启动 HTTP 检索服务（默认端口 8080，--port 0 自动分配）；--watch 可重复，指定文件变更实时监控目录\n"
        "  help             显示本帮助\n"
        "  version          显示版本\n"
        "\n"
        "示例：\n"
        "  docseek index ~/notes --ext .md,.txt --max-mb 10\n"
        "  docseek search 全文检索 --limit 5\n"
        "  docseek locate \"退款流程写在哪一段\"\n"
        "  docseek --json stats\n"
        "  docseek --db /tmp/docseek.db prune\n"
        "  docseek serve --port 8080 --watch ~/notes\n"
        "  docseek --db /data/docseek.db serve --port 0 --watch /data/docs --watch /data/notes\n"
        "  docseek backup /data/docseek-backup.db\n"
        "  docseek restore /data/docseek-backup.db\n";
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
    docseek::SearchWeights weights;
    weights.titleBoost = o.titleBoost;
    weights.phraseBoost = o.phraseBoost;
    docseek::Searcher s(db, weights);
    bool wantExplain = o.explain;

    if (json) {
        std::cout << "{\"query\":\"" << jsonEscape(o.query) << "\",\"hits\":[";
        if (wantExplain) {
            auto hits = s.explain(o.query, o.limit);
            for (size_t i = 0; i < hits.size(); ++i) {
                const auto& e = hits[i];
                const auto& h = e.hit;
                const auto& b = e.breakdown;
                if (i) std::cout << ",";
                std::cout << "{"
                          << "\"doc_id\":" << h.doc_id << ","
                          << "\"path\":\"" << jsonEscape(h.path) << "\","
                          << "\"title\":\"" << jsonEscape(h.title) << "\","
                          << "\"snippet\":\"" << jsonEscape(h.snippet) << "\","
                          << "\"score\":" << std::fixed << std::setprecision(3) << h.score
                          << ",\"file_type\":\"" << jsonEscape(h.file_type) << "\""
                          << ",\"explain\":{\"base_bm25\":" << std::fixed << std::setprecision(3) << b.baseBm25
                          << ",\"title_bonus\":" << std::fixed << std::setprecision(3) << b.titleBonus
                          << ",\"phrase_bonus\":" << std::fixed << std::setprecision(3) << b.phraseBonus
                          << ",\"structural_bonus\":" << std::fixed << std::setprecision(3) << b.structuralBonus
                          << ",\"final\":" << std::fixed << std::setprecision(3) << b.finalScore
                          << "}}";
            }
        } else {
            auto hits = s.search(o.query, o.limit);
            for (size_t i = 0; i < hits.size(); ++i) {
                const auto& h = hits[i];
                if (i) std::cout << ",";
                std::cout << "{"
                          << "\"doc_id\":" << h.doc_id << ","
                          << "\"path\":\"" << jsonEscape(h.path) << "\","
                          << "\"title\":\"" << jsonEscape(h.title) << "\","
                          << "\"snippet\":\"" << jsonEscape(h.snippet) << "\","
                          << "\"score\":" << std::fixed << std::setprecision(3) << h.score
                          << ",\"file_type\":\"" << jsonEscape(h.file_type) << "\""
                          << "}";
            }
        }
        std::cout << "]}\n";
    } else {
        if (wantExplain) {
            auto hits = s.explain(o.query, o.limit);
            if (hits.empty()) {
                std::cout << "没有找到匹配 \"" << o.query << "\" 的文档。\n";
            } else {
                auto fx = [](double v) {
                    std::ostringstream ss;
                    ss << std::fixed << std::setprecision(3) << v;
                    return ss.str();
                };
                for (size_t i = 0; i < hits.size(); ++i) {
                    const auto& e = hits[i];
                    const auto& h = e.hit;
                    const auto& b = e.breakdown;
                    std::cout << (i + 1) << ". " << h.path << "\n";
                    std::cout << "   标题：" << h.title << "\n";
                    std::cout << "   类型：" << (h.file_type.empty() ? "未知" : h.file_type) << "\n";
                    std::cout << "   评分：" << std::fixed << std::setprecision(3) << h.score << "\n";
                    std::cout << "   分项：base_bm25=" << fx(b.baseBm25) << " title=" << fx(b.titleBonus) << " phrase=" << fx(b.phraseBonus) << " structural=" << fx(b.structuralBonus) << "\n";
                    std::cout << "   摘要：" << h.snippet << "\n";
                }
            }
        } else {
            auto hits = s.search(o.query, o.limit);
            if (hits.empty()) {
                std::cout << "没有找到匹配 \"" << o.query << "\" 的文档。\n";
            } else {
                for (size_t i = 0; i < hits.size(); ++i) {
                    const auto& h = hits[i];
                    std::cout << (i + 1) << ". " << h.path << "\n";
                    std::cout << "   标题：" << h.title << "\n";
                    std::cout << "   类型：" << (h.file_type.empty() ? "未知" : h.file_type) << "\n";
                    std::cout << "   评分：" << std::fixed << std::setprecision(3) << h.score << "\n";
                    std::cout << "   摘要：" << h.snippet << "\n";
                }
            }
        }
    }
    return 0;
}

// ASCII 大小写不敏感查找（返回字节偏移，找不到返回 npos）。
size_t findCaseInsensitive(const std::string& hay, const std::string& needle, size_t from) {
    if (needle.empty() || from >= hay.size()) return std::string::npos;
    // 小写拷贝比较（ASCII 部分）。
    auto lower = [](const std::string& s) {
        std::string o = s;
        for (char& c : o) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        return o;
    };
    std::string h = lower(hay.substr(from));
    std::string n = lower(needle);
    size_t p = h.find(n);
    return p == std::string::npos ? p : from + p;
}

// 高亮一行中的命中词（useColor 且为 tty 时加 ANSI 红色）。
std::string highlightLine(const std::string& line, const std::vector<std::string>& terms, bool useColor) {
    if (!useColor || terms.empty()) return line;
    // 按长度降序，单次扫描：每个位置优先匹配最长词。
    std::vector<std::string> sorted = terms;
    std::sort(sorted.begin(), sorted.end(),
              [](const std::string& a, const std::string& b) { return a.size() > b.size(); });
    std::string out;
    out.reserve(line.size() + 32);
    size_t i = 0;
    while (i < line.size()) {
        size_t bestLen = 0;
        for (const auto& t : sorted) {
            if (t.empty() || i + t.size() > line.size()) continue;
            if (findCaseInsensitive(line, t, i) == i) {
                if (t.size() > bestLen) bestLen = t.size();
            }
        }
        if (bestLen > 0) {
            out += "\033[31m";
            out.append(line, i, bestLen);
            out += "\033[0m";
            i += bestLen;
        } else {
            out.push_back(line[i]);
            ++i;
        }
    }
    return out;
}

int cmdLocate(docseek::Database& db, const LocateCmdOpts& o, bool json) {
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);
    docseek::LocateOptions lopts;
    lopts.limit = o.limit;
    std::vector<docseek::Passage> anchors = locator.locate(o.query, lopts);
    docseek::ParsedQuery pq = docseek::parseNaturalQuery(o.query);

    if (json) {
        std::cout << "{\"query\":\"" << jsonEscape(o.query) << "\",\"keywords\":[";
        for (size_t i = 0; i < pq.keywords.size(); ++i) {
            if (i) std::cout << ",";
            std::cout << "\"" << jsonEscape(pq.keywords[i]) << "\"";
        }
        std::cout << "],\"anchors\":[";
        for (size_t i = 0; i < anchors.size(); ++i) {
            const auto& a = anchors[i];
            if (i) std::cout << ",";
            std::cout << "{"
                      << "\"doc_id\":" << a.doc_id << ","
                      << "\"path\":\"" << jsonEscape(a.path) << "\","
                      << "\"line_start\":" << a.line_start << ","
                      << "\"line_end\":" << a.line_end << ","
                      << "\"score\":" << std::fixed << std::setprecision(3) << a.score << ","
                      << "\"matched_terms\":[";
            for (size_t j = 0; j < a.matched_terms.size(); ++j) {
                if (j) std::cout << ",";
                std::cout << "\"" << jsonEscape(a.matched_terms[j]) << "\"";
            }
            std::cout << "],\"text\":\"" << jsonEscape(a.text) << "\"}";
        }
        std::cout << "]}\n";
        return 0;
    }

    if (anchors.empty()) {
        std::cout << "没有找到与 \"" << o.query << "\" 相关的原文段落。\n"
                  << "换个说法再问一次试试（比如直接说关键词）。\n";
        return 0;
    }
#if defined(__linux__)
    bool useColor = ::isatty(STDOUT_FILENO) != 0;
#else
    bool useColor = false;
#endif
    std::vector<std::string> terms = pq.keywords;
    terms.insert(terms.end(), pq.phrases.begin(), pq.phrases.end());
    for (size_t i = 0; i < anchors.size(); ++i) {
        const auto& a = anchors[i];
        std::cout << (i + 1) << ". " << a.path << ":" << a.line_start << "-" << a.line_end
                  << "  （评分 " << std::fixed << std::setprecision(3) << a.score << "）\n";
        std::istringstream iss(a.text);
        std::string line;
        int ln = a.line_start;
        while (std::getline(iss, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            std::cout << "    " << ln << " | " << highlightLine(line, terms, useColor) << "\n";
            ++ln;
        }
        std::cout << "\n";
    }
    return 0;
}

int cmdBackup(docseek::Database& db, const std::string& dest, bool json) {
    docseek::Database::backup(db.path(), dest);
    std::error_code ec;
    int64_t sz = static_cast<int64_t>(std::filesystem::file_size(dest, ec));
    if (ec) sz = -1;
    if (json) {
        std::cout << "{\"dest\":\"" << jsonEscape(dest) << "\",\"bytes\":" << sz << "}\n";
    } else {
        std::cout << "备份完成：" << dest;
        if (sz >= 0) std::cout << "（" << humanBytes(sz) << "）";
        std::cout << "。\n";
    }
    return 0;
}

int cmdRestore(const std::string& src, const std::string& dbPath, bool json) {
    // 1. 先校验备份文件有效性，无效直接拒绝，不碰当前库
    if (!docseek::Database::isValidDocseekDb(src)) {
        std::cerr << "错误：备份文件无效（不是有效的文溯数据库）：" << src << "\n";
        return 2;
    }
    // 2. 复制到临时文件并验证可打开
    std::string tmp = dbPath + ".restore_tmp";
    std::error_code ec;
    std::filesystem::copy_file(src, tmp,
                               std::filesystem::copy_options::overwrite_existing, ec);
    if (ec) {
        std::cerr << "错误：复制备份文件失败：" << ec.message() << "\n";
        return 2;
    }
    int64_t docs = 0;
    try {
        docseek::Database probe = docseek::Database::open(tmp);
        docs = probe.docCount();
    } catch (const std::exception& e) {
        std::filesystem::remove(tmp, ec);
        std::cerr << "错误：备份文件校验失败：" << e.what() << "\n";
        return 2;
    }
    // 3. 原子替换：删旧库（含 WAL 模式的 -wal/-shm，它们属于旧库不能留），rename 到位
    std::filesystem::remove(dbPath, ec);
    std::filesystem::remove(dbPath + "-wal", ec);
    std::filesystem::remove(dbPath + "-shm", ec);
    std::filesystem::rename(tmp, dbPath, ec);
    if (ec) {
        std::cerr << "错误：替换数据库文件失败：" << ec.message() << "\n";
        return 2;
    }
    if (json) {
        std::cout << "{\"restored\":true,\"db\":\"" << jsonEscape(dbPath)
                  << "\",\"documents\":" << docs << "}\n";
    } else {
        std::cout << "恢复完成：" << dbPath << "（" << docs << " 篇文档）。\n";
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
    LocateCmdOpts locateOpts;
    ServeCmdOpts serveOpts;
    std::vector<std::string> searchParts;
    std::vector<std::string> locateParts;
    std::string backupDest;
    std::string restoreSrc;

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
        } else if (a == "--title-boost" && command == "search") {
            if (i + 1 >= argc) {
                std::cerr << "错误：--title-boost 需要参数\n";
                return 1;
            }
            try {
                double v = std::stod(argv[++i]);
                if (!std::isfinite(v) || v < 0.0 || v > 1000.0) {
                    std::cerr << "错误：--title-boost 参数无效\n";
                    return 1;
                }
                searchOpts.titleBoost = v;
            } catch (...) {
                std::cerr << "错误：--title-boost 参数无效\n";
                return 1;
            }

        } else if (a == "--phrase-boost" && command == "search") {
            if (i + 1 >= argc) {
                std::cerr << "错误：--phrase-boost 需要参数\n";
                return 1;
            }
            try {
                double v = std::stod(argv[++i]);
                if (!std::isfinite(v) || v < 0.0 || v > 1000.0) {
                    std::cerr << "错误：--phrase-boost 参数无效\n";
                    return 1;
                }
                searchOpts.phraseBoost = v;
            } catch (...) {
                std::cerr << "错误：--phrase-boost 参数无效\n";
                return 1;
            }

        } else if (a == "--explain" && command == "search") {
            searchOpts.explain = true;
        } else if (a == "--limit" && (command == "search" || command == "locate")) {

            if (i + 1 >= argc) {
                std::cerr << "错误：--limit 需要参数\n";
                return 1;
            }
            try {
                int v = static_cast<int>(std::stoll(argv[++i]));
                if (command == "locate") {
                    locateOpts.limit = v;
                    if (locateOpts.limit <= 0) locateOpts.limit = 5;
                } else {
                    searchOpts.limit = v;
                    if (searchOpts.limit <= 0) searchOpts.limit = 20;
                }
            } catch (...) {
                std::cerr << "错误：--limit 参数无效\n";
                return 1;
            }
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
            } else if (command == "locate") {
                locateParts.push_back(a);
            } else if (command == "backup") {
                if (!backupDest.empty()) {
                    std::cerr << "错误：backup 只接受一个目标路径\n";
                    return 1;
                }
                backupDest = a;
            } else if (command == "restore") {
                if (!restoreSrc.empty()) {
                    std::cerr << "错误：restore 只接受一个备份文件路径\n";
                    return 1;
                }
                restoreSrc = a;
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
    if (command == "locate") {
        std::ostringstream oss;
        for (size_t i = 0; i < locateParts.size(); ++i) {
            if (i) oss << " ";
            oss << locateParts[i];
        }
        locateOpts.query = oss.str();
        if (locateOpts.query.empty()) {
            std::cerr << "错误：locate 命令需要查询字符串\n";
            printUsage();
            return 1;
        }
    }
    if (command == "backup" && backupDest.empty()) {
        std::cerr << "错误：backup 命令需要目标路径\n";
        printUsage();
        return 1;
    }
    if (command == "restore" && restoreSrc.empty()) {
        std::cerr << "错误：restore 命令需要备份文件路径\n";
        printUsage();
        return 1;
    }
    if (command != "index" && command != "search" && command != "locate" &&
        command != "stats" && command != "prune" && command != "serve" &&
        command != "backup" && command != "restore") {
        std::cerr << "错误：未知命令 " << command << "\n";
        printUsage();
        return 1;
    }

    try {
        std::string dbPath = resolveDbPath(g.dbPath);
        // restore 必须在打开当前库之前完成文件替换（否则 SQLite 句柄会占住旧文件）
        if (command == "restore") return cmdRestore(restoreSrc, dbPath, g.json);
        docseek::Database db = docseek::Database::open(dbPath);

        if (command == "index") return cmdIndex(db, indexOpts, g.json);
        if (command == "search") return cmdSearch(db, searchOpts, g.json);
        if (command == "locate") return cmdLocate(db, locateOpts, g.json);
        if (command == "stats") return cmdStats(db, g.json);
        if (command == "prune") return cmdPrune(db, g.json);
        if (command == "backup") return cmdBackup(db, backupDest, g.json);
        if (command == "serve") return cmdServe(db, serveOpts);
    } catch (const std::exception& e) {
        std::cerr << "错误：" << e.what() << "\n";
        return 2;
    }
    return 0;
}
