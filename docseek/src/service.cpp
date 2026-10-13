#include "docseek/service.h"

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/http_server.h"
#include "docseek/indexer.h"
#include "docseek/searcher.h"
#include "docseek/locator.h"
#include "docseek/query_parser.h"
#include "docseek/watcher.h"
#include "web_ui.h"

namespace docseek {

namespace {

std::string jsonEscape(const std::string& in) {
    std::string out;
    out.reserve(in.size() + 8);
    for (unsigned char c : in) {
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
                    static const char* hex = "0123456789abcdef";
                    out += "\\u00";
                    out += hex[(c >> 4) & 0xF];
                    out += hex[c & 0xF];
                } else {
                    out += static_cast<char>(c);
                }
                break;
        }
    }
    return out;
}

std::optional<std::string> extractJsonString(const std::string& body, const std::string& key) {
    std::string needle = "\"" + key + "\"";
    size_t pos = body.find(needle);
    if (pos == std::string::npos) return std::nullopt;
    pos += needle.size();
    while (pos < body.size() && (body[pos] == ' ' || body[pos] == '\t' ||
                                 body[pos] == '\n' || body[pos] == '\r')) {
        ++pos;
    }
    if (pos >= body.size() || body[pos] != ':') return std::nullopt;
    ++pos;
    while (pos < body.size() && (body[pos] == ' ' || body[pos] == '\t' ||
                                 body[pos] == '\n' || body[pos] == '\r')) {
        ++pos;
    }
    if (pos >= body.size() || body[pos] != '"') return std::nullopt;
    ++pos;
    std::string result;
    while (pos < body.size()) {
        char c = body[pos];
        if (c == '"') {
            return result;
        }
        if (c == '\\') {
            ++pos;
            if (pos >= body.size()) return std::nullopt;
            char e = body[pos];
            switch (e) {
                case '"': result += '"'; break;
                case '\\': result += '\\'; break;
                case '/': result += '/'; break;
                case 'b': result += '\b'; break;
                case 'f': result += '\f'; break;
                case 'n': result += '\n'; break;
                case 'r': result += '\r'; break;
                case 't': result += '\t'; break;
                case 'u': {
                    if (pos + 4 >= body.size()) return std::nullopt;
                    unsigned int cp = 0;
                    for (int i = 1; i <= 4; ++i) {
                        char h = body[pos + i];
                        cp <<= 4;
                        if (h >= '0' && h <= '9') cp |= static_cast<unsigned>(h - '0');
                        else if (h >= 'a' && h <= 'f') cp |= static_cast<unsigned>(h - 'a' + 10);
                        else if (h >= 'A' && h <= 'F') cp |= static_cast<unsigned>(h - 'A' + 10);
                        else return std::nullopt;
                    }
                    pos += 4;
                    if (cp < 0x80) {
                        result += static_cast<char>(cp);
                    } else if (cp < 0x800) {
                        result += static_cast<char>(0xC0 | (cp >> 6));
                        result += static_cast<char>(0x80 | (cp & 0x3F));
                    } else {
                        result += static_cast<char>(0xE0 | (cp >> 12));
                        result += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
                        result += static_cast<char>(0x80 | (cp & 0x3F));
                    }
                    break;
                }
                default:
                    return std::nullopt;
            }
            ++pos;
        } else {
            result += c;
            ++pos;
        }
    }
    return std::nullopt;
}

std::string formatScore(double s) {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(3) << s;
    return oss.str();
}

}  // namespace

class Service::Impl {
public:
    Impl(Database& db, ServeOptions opts)
        : db_(db), opts_(std::move(opts)), startTime_(std::chrono::steady_clock::now()) {
        for (const auto& dir : opts_.watchDirs) {
            std::error_code ec;
            if (!std::filesystem::exists(dir, ec) || ec) {
                throw std::runtime_error("watch dir does not exist: " + dir);
            }
        }
    }

    void registerRoutes() {
        server_->onGet("/", [this](const HttpRequest&) {
            return HttpResponse::text(kWebUiHtml);
        });

        server_->onGet("/api/health", [this](const HttpRequest&) {
            std::lock_guard<std::mutex> lk(dbMutex_);
            return HttpResponse::json("{\"ok\":true,\"version\":\"0.4.0\"}");
        });

        server_->onGet("/api/stats", [this](const HttpRequest&) {
            std::lock_guard<std::mutex> lk(dbMutex_);
            auto now = std::chrono::steady_clock::now();
            auto uptime = std::chrono::duration_cast<std::chrono::seconds>(now - startTime_).count();
            std::ostringstream oss;
            oss << "{\"documents\":" << db_.docCount()
                << ",\"total_bytes\":" << db_.totalBytes()
                << ",\"db_bytes\":" << db_.dbFileBytes()
                << ",\"uptime_sec\":" << uptime
                << ",\"watched_dirs\":[";
            std::vector<std::string> dirs = watcher_ ? watcher_->watched() : opts_.watchDirs;
            for (size_t i = 0; i < dirs.size(); ++i) {
                if (i) oss << ',';
                oss << '"' << jsonEscape(dirs[i]) << '"';
            }
            oss << "]}";
            return HttpResponse::json(oss.str());
        });

        server_->onGet("/api/search", [this](const HttpRequest& req) {
            std::lock_guard<std::mutex> lk(dbMutex_);
            auto it = req.query.find("q");
            if (it == req.query.end() || it->second.empty()) {
                return HttpResponse::json("{\"error\":\"缺少查询参数 q\"}", 400);
            }
            std::string q = it->second;
            int limit = 20;
            auto lit = req.query.find("limit");
            if (lit != req.query.end() && !lit->second.empty()) {
                try {
                    int parsed = std::stoi(lit->second);
                    if (parsed >= 1 && parsed <= 100) limit = parsed;
                } catch (...) {
                    limit = 20;
                }
            }
            Searcher searcher(db_);
            std::vector<Hit> hits = searcher.search(q, limit);
            std::ostringstream oss;
            oss << "{\"query\":\"" << jsonEscape(q) << "\",\"hits\":[";
            for (size_t i = 0; i < hits.size(); ++i) {
                const Hit& h = hits[i];
                if (i) oss << ',';
                oss << "{\"doc_id\":" << h.doc_id
                    << ",\"path\":\"" << jsonEscape(h.path)
                    << "\",\"title\":\"" << jsonEscape(h.title)
                    << "\",\"snippet\":\"" << jsonEscape(h.snippet)
                    << "\",\"score\":" << formatScore(h.score) << "}";
            }
            oss << "]}";
            return HttpResponse::json(oss.str());
        });

        server_->onGet("/api/locate", [this](const HttpRequest& req) {
            std::lock_guard<std::mutex> lk(dbMutex_);
            auto it = req.query.find("q");
            if (it == req.query.end() || it->second.empty()) {
                return HttpResponse::json("{\"error\":\"缺少查询参数 q\"}", 400);
            }
            std::string q = it->second;
            int limit = 5;
            auto lit = req.query.find("limit");
            if (lit != req.query.end() && !lit->second.empty()) {
                try {
                    int parsed = std::stoi(lit->second);
                    if (parsed >= 1 && parsed <= 100) limit = parsed;
                } catch (...) {
                    limit = 5;
                }
            }
            ParsedQuery pq = parseNaturalQuery(q);
            Searcher searcher(db_);
            Locator locator(db_, searcher);
            LocateOptions lopts;
            lopts.limit = limit;
            std::vector<Passage> anchors = locator.locate(q, lopts);
            std::ostringstream oss;
            oss << "{\"query\":\"" << jsonEscape(q) << "\",\"keywords\":[";
            for (size_t i = 0; i < pq.keywords.size(); ++i) {
                if (i) oss << ',';
                oss << '"' << jsonEscape(pq.keywords[i]) << '"';
            }
            oss << "],\"anchors\":[";
            for (size_t i = 0; i < anchors.size(); ++i) {
                const Passage& a = anchors[i];
                if (i) oss << ',';
                oss << "{\"doc_id\":" << a.doc_id
                    << ",\"path\":\"" << jsonEscape(a.path)
                    << "\",\"line_start\":" << a.line_start
                    << ",\"line_end\":" << a.line_end
                    << ",\"score\":" << formatScore(a.score)
                    << ",\"matched_terms\":[";
                for (size_t j = 0; j < a.matched_terms.size(); ++j) {
                    if (j) oss << ',';
                    oss << '"' << jsonEscape(a.matched_terms[j]) << '"';
                }
                oss << "],\"text\":\"" << jsonEscape(a.text) << "\"}";
            }
            oss << "]}";
            return HttpResponse::json(oss.str());
        });

        server_->onPost("/api/index", [this](const HttpRequest& req) {
            std::lock_guard<std::mutex> lk(dbMutex_);
            auto pathOpt = extractJsonString(req.body, "path");
            if (!pathOpt || pathOpt->empty()) {
                return HttpResponse::json("{\"error\":\"缺少 path\"}", 400);
            }
            const std::string& path = *pathOpt;
            std::error_code ec;
            if (!std::filesystem::exists(path, ec) || ec) {
                return HttpResponse::json("{\"error\":\"路径不存在\"}", 422);
            }
            Indexer indexer(db_, opts_.indexOpts);
            IndexStats stats = indexer.indexPaths({path});
            std::ostringstream oss;
            oss << "{\"scanned\":" << stats.scanned
                << ",\"added\":" << stats.added
                << ",\"updated\":" << stats.updated
                << ",\"unchanged\":" << stats.unchanged
                << ",\"removed\":" << stats.removed
                << ",\"skipped\":" << stats.skipped
                << ",\"errors\":[";
            for (size_t i = 0; i < stats.errors.size(); ++i) {
                if (i) oss << ',';
                oss << '"' << jsonEscape(stats.errors[i]) << '"';
            }
            oss << "]}";
            return HttpResponse::json(oss.str());
        });

        server_->onPost("/api/prune", [this](const HttpRequest&) {
            std::lock_guard<std::mutex> lk(dbMutex_);
            Indexer indexer(db_, opts_.indexOpts);
            size_t removed = indexer.pruneMissing();
            std::ostringstream oss;
            oss << "{\"removed\":" << removed << "}";
            return HttpResponse::json(oss.str());
        });

        server_->onGet("/api/watch", [this](const HttpRequest&) {
            std::lock_guard<std::mutex> lk(dbMutex_);
            std::vector<std::string> dirs = watcher_ ? watcher_->watched() : opts_.watchDirs;
            std::ostringstream oss;
            oss << "{\"dirs\":[";
            for (size_t i = 0; i < dirs.size(); ++i) {
                if (i) oss << ',';
                oss << '"' << jsonEscape(dirs[i]) << '"';
            }
            oss << "]}";
            return HttpResponse::json(oss.str());
        });

        server_->onPost("/api/watch", [this](const HttpRequest& req) {
            std::lock_guard<std::mutex> lk(dbMutex_);
            auto pathOpt = extractJsonString(req.body, "path");
            if (!pathOpt || pathOpt->empty()) {
                return HttpResponse::json("{\"error\":\"缺少 path\"}", 400);
            }
            const std::string& path = *pathOpt;
            if (!watcher_ || !watcher_->add(path)) {
                return HttpResponse::json("{\"error\":\"目录不可用或不存在\"}", 422);
            }
            std::vector<std::string> dirs = watcher_->watched();
            std::ostringstream oss;
            oss << "{\"added\":true,\"dir\":\"" << jsonEscape(path) << "\",\"dirs\":[";
            for (std::size_t i = 0; i < dirs.size(); ++i) {
                if (i != 0) oss << ",";
                oss << "\"" << jsonEscape(dirs[i]) << "\"";
            }
            oss << "]}";
            return HttpResponse::json(oss.str());
        });

        server_->onDelete("/api/watch", [this](const HttpRequest& req) {
            std::lock_guard<std::mutex> lk(dbMutex_);
            auto it = req.query.find("path");
            if (it == req.query.end() || it->second.empty()) {
                return HttpResponse::json("{\"error\":\"缺少 path\"}", 400);
            }
            const std::string& path = it->second;
            if (!watcher_ || !watcher_->remove(path)) {
                return HttpResponse::json("{\"error\":\"该目录不在监控中\"}", 404);
            }
            std::ostringstream oss;
            oss << "{\"removed\":true,\"dir\":\"" << jsonEscape(path) << "\"}";
            return HttpResponse::json(oss.str());
        });
    }

    Database& db_;
    ServeOptions opts_;
    std::chrono::steady_clock::time_point startTime_;
    std::mutex dbMutex_;
    std::mutex runMutex_;
    std::condition_variable runCv_;
    std::atomic<bool> stopRequested_{false};
    std::unique_ptr<HttpServer> server_;
    std::unique_ptr<Watcher> watcher_;
    int actualPort_ = 0;
};

Service::Service(Database& db, ServeOptions opts)
    : impl_(new Impl(db, std::move(opts))) {}

Service::~Service() {
    stop();
    delete impl_;
}

void Service::run() {
    impl_->stopRequested_.store(false);

    impl_->server_ = std::make_unique<HttpServer>();
    impl_->watcher_ = std::make_unique<Watcher>(
        [this](const std::string& path, WatchEvent ev) {
            std::lock_guard<std::mutex> lk(impl_->dbMutex_);
            try {
                if (ev == WatchEvent::Deleted) {
                    impl_->db_.removeByPath(path);
                } else {
                    Indexer indexer(impl_->db_, impl_->opts_.indexOpts);
                    indexer.indexPaths({path});
                }
            } catch (...) {
                // swallow
            }
        },
        800);

    impl_->registerRoutes();

    for (const auto& dir : impl_->opts_.watchDirs) {
        if (!impl_->watcher_->add(dir)) {
            throw std::runtime_error("failed to watch dir: " + dir);
        }
    }

    impl_->server_->start(impl_->opts_.port);
    impl_->actualPort_ = impl_->server_->port();

    {
        std::unique_lock<std::mutex> lk(impl_->runMutex_);
        impl_->runCv_.wait(lk, [this] { return impl_->stopRequested_.load(); });
    }

    if (impl_->server_) {
        impl_->server_->stop();
    }
    impl_->server_.reset();
    impl_->watcher_.reset();
}

void Service::stop() {
    {
        std::lock_guard<std::mutex> lk(impl_->runMutex_);
        impl_->stopRequested_.store(true);
    }
    impl_->runCv_.notify_all();
}

int Service::port() const {
    return impl_->actualPort_;
}

std::vector<std::string> Service::watchedDirs() const {
    if (impl_->watcher_) {
        return impl_->watcher_->watched();
    }
    return impl_->opts_.watchDirs;
}

}  // namespace docseek
