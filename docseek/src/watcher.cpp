#include "docseek/watcher.h"

#include <atomic>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <map>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#ifdef __linux__
#include <sys/inotify.h>
#include <poll.h>
#include <unistd.h>
#endif

namespace docseek {

#ifdef __linux__

namespace fs = std::filesystem;

namespace {

constexpr std::uint32_t kWatchMask =
    IN_CREATE | IN_MODIFY | IN_DELETE | IN_MOVED_FROM | IN_MOVED_TO |
    IN_DELETE_SELF | IN_IGNORED;

std::string normalizePath(const std::string& p) {
  std::error_code ec;
  fs::path abs = fs::absolute(p, ec);
  if (ec) {
    abs = fs::path(p);
  }
  return abs.lexically_normal().string();
}

bool isSelfOrDescendant(const fs::path& candidate, const fs::path& ancestor) {
  auto cit = candidate.begin();
  auto ait = ancestor.begin();
  for (; ait != ancestor.end(); ++ait, ++cit) {
    if (cit == candidate.end() || *cit != *ait) {
      return false;
    }
  }
  return true;
}

}  // namespace

struct Watcher::Impl {
  Callback cb_;
  int debounceMs_;

  int fd_ = -1;
  std::atomic<bool> running_{false};

  std::thread loopThread_;
  std::thread debounceThread_;

  mutable std::mutex mu_;
  // wd -> 绝对规范目录路径
  std::map<int, std::string> wdToPath_;
  // 绝对规范目录路径 -> wd
  std::unordered_map<std::string, int> pathToWd_;
  // 待合并事件：绝对规范路径 -> {事件类型, 最后时间}
  std::map<std::string, std::pair<WatchEvent, std::chrono::steady_clock::time_point>> pending_;

  Impl(Callback cb, int debounceMs)
      : cb_(std::move(cb)), debounceMs_(debounceMs < 0 ? 0 : debounceMs) {
    fd_ = ::inotify_init1(IN_CLOEXEC | IN_NONBLOCK);
    if (fd_ < 0) {
      throw std::runtime_error(std::string("inotify_init1 failed: ") + std::strerror(errno));
    }
    running_.store(true, std::memory_order_release);
    loopThread_ = std::thread([this] { loop(); });
    debounceThread_ = std::thread([this] { debounceLoop(); });
  }

  ~Impl() {
    running_.store(false, std::memory_order_release);
    // 先 join 线程再 close fd：loop() 用 poll 超时轮询 running_，不会卡在 read()；
    // 若先 close 而 read 仍阻塞，read 持有的文件描述引用会导致 join 永远等不到返回。
    if (loopThread_.joinable()) {
      loopThread_.join();
    }
    if (debounceThread_.joinable()) {
      debounceThread_.join();
    }
    if (fd_ >= 0) {
      ::close(fd_);
      fd_ = -1;
    }
  }

  // 递归给目录及其全部子孙目录加 watch；返回成功添加的目录数（>=0）
  int addWatchRecursive(const std::string& normDir) {
    std::error_code ec;
    if (!fs::is_directory(normDir, ec) || ec) {
      return 0;
    }
    int count = 0;
    auto addOne = [&](const fs::path& dir) -> bool {
      std::string dirStr = dir.string();
      {
        std::lock_guard<std::mutex> lk(mu_);
        if (pathToWd_.find(dirStr) != pathToWd_.end()) {
          return true;
        }
      }
      int wd = ::inotify_add_watch(fd_, dirStr.c_str(), kWatchMask);
      if (wd < 0) {
        return false;
      }
      {
        std::lock_guard<std::mutex> lk(mu_);
        // 可能并发重复添加，若已有映射则以先到为准，移除新的
        auto it = wdToPath_.find(wd);
        if (it != wdToPath_.end()) {
          // wd 被复用或重复，更新映射
          pathToWd_.erase(it->second);
          it->second = dirStr;
          pathToWd_[dirStr] = wd;
        } else {
          wdToPath_[wd] = dirStr;
          pathToWd_[dirStr] = wd;
        }
      }
      ++count;
      return true;
    };

    if (!addOne(fs::path(normDir))) {
      return count;
    }
    fs::recursive_directory_iterator rit(normDir, fs::directory_options::skip_permission_denied, ec);
    if (ec) {
      return count;
    }
    fs::recursive_directory_iterator end;
    for (; rit != end; rit.increment(ec)) {
      if (ec) {
        break;
      }
      if (rit->is_directory(ec) && !ec) {
        addOne(rit->path());
      }
    }
    return count;
  }

  void removeWatchRecursive(const std::string& normDir) {
    std::vector<int> wdsToRemove;
    std::vector<std::string> pathsToRemove;
    {
      std::lock_guard<std::mutex> lk(mu_);
      for (auto it = pathToWd_.begin(); it != pathToWd_.end();) {
        const std::string& p = it->first;
        bool match = (p == normDir);
        if (!match) {
          std::error_code ec;
          match = isSelfOrDescendant(fs::path(p), fs::path(normDir));
          (void)ec;
        }
        if (match) {
          wdsToRemove.push_back(it->second);
          pathsToRemove.push_back(p);
          it = pathToWd_.erase(it);
        } else {
          ++it;
        }
      }
      for (const auto& p : pathsToRemove) {
        pending_.erase(p);
      }
    }
    for (int wd : wdsToRemove) {
      {
        std::lock_guard<std::mutex> lk(mu_);
        wdToPath_.erase(wd);
      }
      ::inotify_rm_watch(fd_, wd);
    }
  }

  void handleCreate(const std::string& dir, const std::string& name, bool isDir) {
    if (!isDir) {
      return;
    }
    std::string child = normalizePath((fs::path(dir) / name).string());
    addWatchRecursive(child);
  }

  void recordEvent(const std::string& path, WatchEvent kind) {
    std::lock_guard<std::mutex> lk(mu_);
    auto it = pending_.find(path);
    auto now = std::chrono::steady_clock::now();
    if (it == pending_.end()) {
      pending_[path] = {kind, now};
      return;
    }
    WatchEvent& existing = it->second.first;
    if (existing == WatchEvent::Deleted) {
      it->second.second = now;
      return;
    }
    if (kind == WatchEvent::Deleted) {
      existing = WatchEvent::Deleted;
    } else if (existing != WatchEvent::Created && kind == WatchEvent::Created) {
      existing = WatchEvent::Created;
    } else if (existing == WatchEvent::Modified && kind == WatchEvent::Created) {
      existing = WatchEvent::Created;
    }
    it->second.second = now;
  }

  void loop() {
    std::vector<char> buf(64 * 1024);
    struct pollfd pfd;
    pfd.fd = fd_;
    pfd.events = POLLIN;
    while (running_.load(std::memory_order_acquire)) {
      // poll 超时轮询：fd 已设 IN_NONBLOCK；即使无事件也能定期检查 running_，
      // 析构时 join 最多等待一个超时周期，不依赖 close() 唤醒 read()。
      int pr = ::poll(&pfd, 1, 200);
      if (pr < 0) {
        if (errno == EINTR) {
          continue;
        }
        break;
      }
      if (pr == 0) {
        continue;  // 超时：回环检查 running_
      }
      ssize_t n = ::read(fd_, buf.data(), buf.size());
      if (n <= 0) {
        if (n < 0 && (errno == EINTR || errno == EAGAIN)) {
          continue;
        }
        break;
      }
      ssize_t off = 0;
      while (off < n) {
        auto* ev = reinterpret_cast<struct inotify_event*>(buf.data() + off);
        std::string dir;
        bool haveDir = false;
        {
          std::lock_guard<std::mutex> lk(mu_);
          auto it = wdToPath_.find(ev->wd);
          if (it != wdToPath_.end()) {
            dir = it->second;
            haveDir = true;
          }
        }
        if (ev->mask & IN_IGNORED) {
          std::lock_guard<std::mutex> lk(mu_);
          auto it = wdToPath_.find(ev->wd);
          if (it != wdToPath_.end()) {
            pathToWd_.erase(it->second);
            wdToPath_.erase(it);
          }
        } else if (haveDir) {
          std::string name(ev->name);
          std::string full = name.empty() ? dir : normalizePath((fs::path(dir) / name).string());
          bool isDir = (ev->mask & IN_ISDIR) != 0;
          if (ev->mask & (IN_CREATE | IN_MOVED_TO)) {
            if (isDir) {
              handleCreate(dir, name, true);
            }
            recordEvent(full, WatchEvent::Created);
          }
          if (ev->mask & (IN_MODIFY | IN_MOVED_FROM)) {
            recordEvent(full, WatchEvent::Modified);
          }
          if (ev->mask & IN_DELETE) {
            recordEvent(full, WatchEvent::Deleted);
          }
          if (ev->mask & IN_DELETE_SELF) {
            std::lock_guard<std::mutex> lk(mu_);
            auto it = wdToPath_.find(ev->wd);
            if (it != wdToPath_.end()) {
              pathToWd_.erase(it->second);
              wdToPath_.erase(it);
            }
          }
        }
        off += static_cast<ssize_t>(sizeof(struct inotify_event) + ev->len);
      }
    }
  }

  void debounceLoop() {
    while (running_.load(std::memory_order_acquire)) {
      std::this_thread::sleep_for(std::chrono::milliseconds(200));
      std::vector<std::pair<std::string, WatchEvent>> ready;
      auto now = std::chrono::steady_clock::now();
      {
        std::lock_guard<std::mutex> lk(mu_);
        for (auto it = pending_.begin(); it != pending_.end();) {
          auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                             now - it->second.second)
                             .count();
          if (elapsed > debounceMs_) {
            ready.emplace_back(it->first, it->second.first);
            it = pending_.erase(it);
          } else {
            ++it;
          }
        }
      }
      for (const auto& item : ready) {
        if (!cb_) {
          continue;
        }
        try {
          cb_(item.first, item.second);
        } catch (...) {
        }
      }
    }
  }
};

Watcher::Watcher(Callback cb, int debounceMs)
    : impl_(std::make_unique<Impl>(std::move(cb), debounceMs)) {}

Watcher::~Watcher() = default;

bool Watcher::add(const std::string& dir) {
  if (!impl_) {
    return false;
  }
  std::error_code ec;
  fs::path p = fs::absolute(dir, ec);
  if (ec) {
    return false;
  }
  std::string norm = p.lexically_normal().string();
  if (!fs::is_directory(norm, ec) || ec) {
    return false;
  }
  {
    std::lock_guard<std::mutex> lk(impl_->mu_);
    if (impl_->pathToWd_.find(norm) != impl_->pathToWd_.end()) {
      return true;
    }
  }
  impl_->addWatchRecursive(norm);
  return true;
}

bool Watcher::remove(const std::string& dir) {
  if (!impl_) {
    return false;
  }
  std::error_code ec;
  fs::path p = fs::absolute(dir, ec);
  if (ec) {
    return false;
  }
  std::string norm = p.lexically_normal().string();
  {
    std::lock_guard<std::mutex> lk(impl_->mu_);
    if (impl_->pathToWd_.find(norm) == impl_->pathToWd_.end()) {
      return false;
    }
  }
  impl_->removeWatchRecursive(norm);
  return true;
}

std::vector<std::string> Watcher::watched() const {
  std::vector<std::string> out;
  if (!impl_) {
    return out;
  }
  std::lock_guard<std::mutex> lk(impl_->mu_);
  out.reserve(impl_->pathToWd_.size());
  for (const auto& kv : impl_->pathToWd_) {
    out.push_back(kv.first);
  }
  return out;
}

#else  // !__linux__

struct Watcher::Impl {};

Watcher::Watcher(Callback /*cb*/, int /*debounceMs*/) {
  throw std::runtime_error("文件变更监控仅支持 Linux");
}

Watcher::~Watcher() = default;

bool Watcher::add(const std::string& /*dir*/) { return false; }

bool Watcher::remove(const std::string& /*dir*/) { return false; }

std::vector<std::string> Watcher::watched() const { return {}; }

#endif  // __linux__

}  // namespace docseek
