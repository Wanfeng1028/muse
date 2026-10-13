#include "docseek/http_server.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <atomic>
#include <cerrno>
#include <cstring>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>

namespace docseek {

namespace {

std::string toLower(const std::string& s) {
  std::string out;
  out.reserve(s.size());
  for (char c : s) {
    if (c >= 'A' && c <= 'Z') {
      out.push_back(static_cast<char>(c - 'A' + 'a'));
    } else {
      out.push_back(c);
    }
  }
  return out;
}

std::string trim(const std::string& s) {
  std::size_t b = 0;
  std::size_t e = s.size();
  while (b < e && (s[b] == ' ' || s[b] == '\t' || s[b] == '\r' || s[b] == '\n')) {
    ++b;
  }
  while (e > b && (s[e - 1] == ' ' || s[e - 1] == '\t' || s[e - 1] == '\r' || s[e - 1] == '\n')) {
    --e;
  }
  return s.substr(b, e - b);
}

int hexVal(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

std::string urlDecode(const std::string& s) {
  std::string out;
  out.reserve(s.size());
  std::size_t i = 0;
  while (i < s.size()) {
    char c = s[i];
    if (c == '+') {
      out.push_back(' ');
      ++i;
    } else if (c == '%' && i + 2 < s.size()) {
      int hi = hexVal(s[i + 1]);
      int lo = hexVal(s[i + 2]);
      if (hi >= 0 && lo >= 0) {
        out.push_back(static_cast<char>((hi << 4) | lo));
        i += 3;
      } else {
        out.push_back(c);
        ++i;
      }
    } else {
      out.push_back(c);
      ++i;
    }
  }
  return out;
}

const char* reasonPhrase(int status) {
  switch (status) {
    case 200: return "OK";
    case 400: return "Bad Request";
    case 404: return "Not Found";
    case 405: return "Method Not Allowed";
    case 413: return "Payload Too Large";
    case 500: return "Internal Server Error";
    default: return "OK";
  }
}

constexpr std::size_t kMaxBody = 8u * 1024u * 1024u;

}  // namespace

HttpResponse HttpResponse::json(const std::string& body, int status) {
  HttpResponse r;
  r.status = status;
  r.content_type = "application/json; charset=utf-8";
  r.body = body;
  return r;
}

HttpResponse HttpResponse::text(const std::string& body, int status) {
  HttpResponse r;
  r.status = status;
  r.content_type = "text/html; charset=utf-8";
  r.body = body;
  return r;
}

HttpResponse HttpResponse::err(int status, const std::string& msg) {
  HttpResponse r;
  r.status = status;
  r.content_type = "application/json; charset=utf-8";
  r.body = std::string("{\"error\":\"") + msg + "\"}";
  return r;
}

struct HttpServer::Impl {
  std::map<std::string, Handler> getMap;
  std::map<std::string, Handler> postMap;
  std::map<std::string, Handler> delMap;
  int listenFd = -1;
  std::atomic<bool> running{false};
  std::thread acceptThread;
  int actualPort = -1;
};

HttpServer::HttpServer() : impl_(new Impl()) {}

HttpServer::~HttpServer() {
  stop();
  delete impl_;
  impl_ = nullptr;
}

void HttpServer::onGet(const std::string& path, Handler h) {
  impl_->getMap[path] = std::move(h);
}

void HttpServer::onPost(const std::string& path, Handler h) {
  impl_->postMap[path] = std::move(h);
}

void HttpServer::onDelete(const std::string& path, Handler h) {
  impl_->delMap[path] = std::move(h);
}

namespace {

bool readLine(int fd, std::string& out) {
  out.clear();
  char c = 0;
  while (true) {
    ssize_t n = ::recv(fd, &c, 1, 0);
    if (n <= 0) return false;
    if (c == '\n') {
      if (!out.empty() && out.back() == '\r') out.pop_back();
      return true;
    }
    out.push_back(c);
    if (out.size() > 64 * 1024) return false;
  }
}

bool readExact(int fd, std::string& out, std::size_t n) {
  out.clear();
  out.reserve(n);
  std::size_t got = 0;
  char buf[8192];
  while (got < n) {
    std::size_t want = n - got;
    if (want > sizeof(buf)) want = sizeof(buf);
    ssize_t r = ::recv(fd, buf, want, 0);
    if (r <= 0) return false;
    out.append(buf, static_cast<std::size_t>(r));
    got += static_cast<std::size_t>(r);
  }
  return true;
}

void writeAll(int fd, const std::string& data) {
  std::size_t sent = 0;
  while (sent < data.size()) {
    ssize_t n = ::send(fd, data.data() + sent, data.size() - sent, MSG_NOSIGNAL);
    if (n <= 0) return;
    sent += static_cast<std::size_t>(n);
  }
}

void sendResponse(int fd, const HttpResponse& resp) {
  std::string out;
  out.reserve(128 + resp.body.size());
  out += "HTTP/1.1 ";
  out += std::to_string(resp.status);
  out += ' ';
  out += reasonPhrase(resp.status);
  out += "\r\nContent-Type: ";
  out += resp.content_type;
  out += "\r\nContent-Length: ";
  out += std::to_string(resp.body.size());
  out += "\r\nConnection: close\r\n\r\n";
  out += resp.body;
  writeAll(fd, out);
}

}  // namespace

void HttpServer::start(int port) {
  if (impl_->running.load()) {
    throw std::runtime_error("server already running");
  }

  int fd = ::socket(AF_INET, SOCK_STREAM, 0);
  if (fd < 0) {
    throw std::runtime_error(std::string("socket failed: ") + std::strerror(errno));
  }

  int opt = 1;
  if (::setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)) < 0) {
    int err = errno;
    ::close(fd);
    throw std::runtime_error(std::string("setsockopt failed: ") + std::strerror(err));
  }

  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_addr.s_addr = htonl(INADDR_ANY);
  addr.sin_port = htons(static_cast<uint16_t>(port));

  if (::bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
    int err = errno;
    ::close(fd);
    throw std::runtime_error(std::string("bind failed: ") + std::strerror(err));
  }

  if (::listen(fd, 64) < 0) {
    int err = errno;
    ::close(fd);
    throw std::runtime_error(std::string("listen failed: ") + std::strerror(err));
  }

  int actual = port;
  if (port == 0) {
    sockaddr_in bound{};
    socklen_t len = sizeof(bound);
    if (::getsockname(fd, reinterpret_cast<sockaddr*>(&bound), &len) == 0) {
      actual = ntohs(bound.sin_port);
    } else {
      int err = errno;
      ::close(fd);
      throw std::runtime_error(std::string("getsockname failed: ") + std::strerror(err));
    }
  }

  impl_->listenFd = fd;
  impl_->actualPort = actual;
  impl_->running.store(true);

  impl_->acceptThread = std::thread([this]() {
    int lfd = impl_->listenFd;
    while (impl_->running.load()) {
      sockaddr_in cli{};
      socklen_t clen = sizeof(cli);
      int cfd = ::accept(lfd, reinterpret_cast<sockaddr*>(&cli), &clen);
      if (cfd < 0) {
        if (!impl_->running.load()) break;
        if (errno == EINTR) continue;
        break;
      }
      std::thread([this, cfd]() {
        // handle connection
        std::string line;
        if (!readLine(cfd, line)) {
          ::close(cfd);
          return;
        }
        // parse request line
        std::size_t sp1 = line.find(' ');
        std::size_t sp2 = (sp1 == std::string::npos) ? std::string::npos : line.find(' ', sp1 + 1);
        if (sp1 == std::string::npos || sp2 == std::string::npos) {
          HttpResponse bad = HttpResponse::err(400, "bad request");
          sendResponse(cfd, bad);
          ::close(cfd);
          return;
        }
        HttpRequest req;
        req.method = line.substr(0, sp1);
        req.target = line.substr(sp1 + 1, sp2 - sp1 - 1);
        // headers
        bool chunked = false;
        std::size_t contentLength = 0;
        while (true) {
          std::string hline;
          if (!readLine(cfd, hline)) {
            ::close(cfd);
            return;
          }
          if (hline.empty()) break;
          std::size_t colon = hline.find(':');
          if (colon == std::string::npos) continue;
          std::string key = toLower(trim(hline.substr(0, colon)));
          std::string val = trim(hline.substr(colon + 1));
          if (key == "transfer-encoding" && toLower(val).find("chunked") != std::string::npos) {
            chunked = true;
          }
          if (key == "content-length") {
            try {
              contentLength = static_cast<std::size_t>(std::stoull(val));
            } catch (...) {
              contentLength = 0;
            }
          }
          req.headers[key] = val;
        }
        if (chunked) {
          HttpResponse bad = HttpResponse::err(400, "chunked not supported");
          sendResponse(cfd, bad);
          ::close(cfd);
          return;
        }
        if (contentLength > kMaxBody) {
          HttpResponse big = HttpResponse::err(413, "payload too large");
          sendResponse(cfd, big);
          ::close(cfd);
          return;
        }
        if (contentLength > 0) {
          if (!readExact(cfd, req.body, contentLength)) {
            ::close(cfd);
            return;
          }
        }
        // parse target
        std::string rawPath = req.target;
        std::string queryStr;
        std::size_t qpos = req.target.find('?');
        if (qpos != std::string::npos) {
          rawPath = req.target.substr(0, qpos);
          queryStr = req.target.substr(qpos + 1);
        }
        req.path = urlDecode(rawPath);
        if (!queryStr.empty()) {
          std::size_t start = 0;
          while (start <= queryStr.size()) {
            std::size_t amp = queryStr.find('&', start);
            std::string pair = (amp == std::string::npos) ? queryStr.substr(start)
                                                          : queryStr.substr(start, amp - start);
            if (!pair.empty()) {
              std::size_t eq = pair.find('=');
              std::string k;
              std::string v;
              if (eq == std::string::npos) {
                k = urlDecode(pair);
              } else {
                k = urlDecode(pair.substr(0, eq));
                v = urlDecode(pair.substr(eq + 1));
              }
              req.query[k] = v;
            }
            if (amp == std::string::npos) break;
            start = amp + 1;
          }
        }

        // route
        const std::map<std::string, Handler>* primary = nullptr;
        const std::map<std::string, Handler>* others[2] = {nullptr, nullptr};
        if (req.method == "GET") {
          primary = &impl_->getMap;
          others[0] = &impl_->postMap;
          others[1] = &impl_->delMap;
        } else if (req.method == "POST") {
          primary = &impl_->postMap;
          others[0] = &impl_->getMap;
          others[1] = &impl_->delMap;
        } else if (req.method == "DELETE") {
          primary = &impl_->delMap;
          others[0] = &impl_->getMap;
          others[1] = &impl_->postMap;
        }

        HttpResponse resp;
        if (primary == nullptr) {
          resp = HttpResponse::err(404, "未找到");
        } else {
          auto it = primary->find(req.path);
          if (it != primary->end()) {
            try {
              resp = it->second(req);
            } catch (...) {
              resp = HttpResponse::err(500, "内部错误");
            }
          } else {
            bool foundElsewhere = false;
            for (int i = 0; i < 2; ++i) {
              if (others[i] != nullptr && others[i]->find(req.path) != others[i]->end()) {
                foundElsewhere = true;
                break;
              }
            }
            if (foundElsewhere) {
              resp = HttpResponse::err(405, "method not allowed");
            } else {
              resp = HttpResponse::err(404, "未找到");
            }
          }
        }

        sendResponse(cfd, resp);
        ::close(cfd);
      }).detach();
    }
  });
}

void HttpServer::stop() {
  if (impl_ == nullptr) return;
  bool wasRunning = impl_->running.exchange(false);
  int lfd = impl_->listenFd;
  if (lfd >= 0) {
    ::shutdown(lfd, SHUT_RDWR);
    ::close(lfd);
    impl_->listenFd = -1;
  }
  if (impl_->acceptThread.joinable()) {
    impl_->acceptThread.join();
  }
  impl_->actualPort = -1;
  (void)wasRunning;
}

int HttpServer::port() const {
  if (impl_ == nullptr) return -1;
  if (!impl_->running.load()) return -1;
  return impl_->actualPort;
}

}  // namespace docseek
