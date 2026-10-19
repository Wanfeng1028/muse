// tests/test_watcher.cpp
// Watcher 单元测试：验证 Linux inotify 实时监控的基本行为。
// 非 Linux 平台直接跳过。

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <unistd.h>

#include "docseek/watcher.h"

namespace fs = std::filesystem;

#ifndef __linux__
TEST(WatcherTest, NonLinuxSkip) { GTEST_SKIP() << "Watcher 仅在 Linux 上运行"; }
#else

namespace {

// 规范路径：绝对化 + 词法归一
std::string Norm(const fs::path& p) {
    return fs::absolute(p).lexically_normal().string();
}

// 轮询等待：在 deadline 内每 100ms 检查一次 predicate
template <typename Pred>
bool WaitFor(Pred pred, std::chrono::milliseconds deadline) {
    const auto start = std::chrono::steady_clock::now();
    while (std::chrono::steady_clock::now() - start < deadline) {
        if (pred()) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    return pred();
}

}  // namespace

class WatcherTest : public ::testing::Test {
 protected:
    void SetUp() override {
        dir_ = fs::temp_directory_path() /
               ("docseek_watch_test_" + std::to_string(::getpid()));
        std::error_code ec;
        fs::remove_all(dir_, ec);
        fs::create_directories(dir_, ec);
        ASSERT_TRUE(fs::exists(dir_));
    }

    void TearDown() override {
        std::error_code ec;
        fs::remove_all(dir_, ec);
    }

    // 清空事件列表（线程安全）
    void ClearEvents() {
        std::lock_guard<std::mutex> lk(m_);
        events_.clear();
    }

    // 在事件列表中查找匹配路径的任意事件
    bool HasAnyEvent(const std::string& path) {
        std::lock_guard<std::mutex> lk(m_);
        for (const auto& e : events_) {
            if (e.first == path) return true;
        }
        return false;
    }

    // 在事件列表中查找匹配路径且类型属于集合的事件
    bool HasEventIn(const std::string& path,
                    std::initializer_list<docseek::WatchEvent> kinds) {
        std::lock_guard<std::mutex> lk(m_);
        for (const auto& e : events_) {
            if (e.first != path) continue;
            for (auto k : kinds) {
                if (e.second == k) return true;
            }
        }
        return false;
    }

    fs::path dir_;
    std::mutex m_;
    std::vector<std::pair<std::string, docseek::WatchEvent>> events_;
};

// 基本写入：应产生 Created 或 Modified 事件
TEST_F(WatcherTest, WriteFile) {
    docseek::Watcher w(
        [&](const fs::path& p, docseek::WatchEvent ev) {
            std::lock_guard<std::mutex> lk(m_);
            events_.emplace_back(Norm(p), ev);
        },
        300);

    ASSERT_TRUE(w.add(dir_));
    const auto watched = w.watched();
    const std::string want = Norm(dir_);
    bool found = false;
    for (const auto& s : watched) {
        if (s == want) { found = true; break; }
    }
    ASSERT_TRUE(found) << "watched() 应包含规范路径: " << want;

    const fs::path a = dir_ / "a.txt";
    {
        std::ofstream ofs(a, std::ios::binary | std::ios::trunc);
        ofs << "hello";
    }

    const std::string aNorm = Norm(a);
    const bool ok = WaitFor(
        [&]() {
            return HasEventIn(aNorm, {docseek::WatchEvent::Created,
                                      docseek::WatchEvent::Modified});
        },
        std::chrono::milliseconds(8000));
    EXPECT_TRUE(ok) << "未在期限内观察到 a.txt 的 Created/Modified 事件";
}

// 修改文件：清空事件后重写，应出现 Modified（或 Created）
TEST_F(WatcherTest, ModifyFile) {
    const fs::path a = dir_ / "a.txt";
    {
        std::ofstream ofs(a, std::ios::binary | std::ios::trunc);
        ofs << "hello";
    }

    docseek::Watcher w(
        [&](const fs::path& p, docseek::WatchEvent ev) {
            std::lock_guard<std::mutex> lk(m_);
            events_.emplace_back(Norm(p), ev);
        },
        300);
    ASSERT_TRUE(w.add(dir_));

    // 等待首次建立监控并消化已有事件
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    ClearEvents();

    {
        std::ofstream ofs(a, std::ios::binary | std::ios::trunc);
        ofs << "world-changed";
    }

    const std::string aNorm = Norm(a);
    const bool ok = WaitFor(
        [&]() { return HasAnyEvent(aNorm); },
        std::chrono::milliseconds(8000));
    EXPECT_TRUE(ok) << "未在期限内观察到 a.txt 的事件";
}

// 删除文件：清空事件后 remove，应出现 Deleted
TEST_F(WatcherTest, DeleteFile) {
    const fs::path a = dir_ / "a.txt";
    {
        std::ofstream ofs(a, std::ios::binary | std::ios::trunc);
        ofs << "hello";
    }

    docseek::Watcher w(
        [&](const fs::path& p, docseek::WatchEvent ev) {
            std::lock_guard<std::mutex> lk(m_);
            events_.emplace_back(Norm(p), ev);
        },
        300);
    ASSERT_TRUE(w.add(dir_));

    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    ClearEvents();

    std::error_code ec;
    fs::remove(a, ec);
    ASSERT_FALSE(ec) << "删除 a.txt 失败: " << ec.message();

    const std::string aNorm = Norm(a);
    const bool ok = WaitFor(
        [&]() { return HasEventIn(aNorm, {docseek::WatchEvent::Deleted}); },
        std::chrono::milliseconds(8000));
    EXPECT_TRUE(ok) << "未在期限内观察到 a.txt 的 Deleted 事件";
}

// 递归监控新子目录：创建 sub/ 后写入 sub/b.txt，应观察到事件
TEST_F(WatcherTest, SubDir) {
    docseek::Watcher w(
        [&](const fs::path& p, docseek::WatchEvent ev) {
            std::lock_guard<std::mutex> lk(m_);
            events_.emplace_back(Norm(p), ev);
        },
        300);
    ASSERT_TRUE(w.add(dir_));

    std::this_thread::sleep_for(std::chrono::milliseconds(300));
    ClearEvents();

    const fs::path sub = dir_ / "sub";
    std::error_code ec;
    fs::create_directory(sub, ec);
    ASSERT_FALSE(ec) << "创建子目录失败: " << ec.message();

    // 根因：新建子目录的 inotify watch 是 loop 线程收到父目录 IN_CREATE
    // 后才异步装上的；若在其就绪前创建 b.txt，该事件不会投递给尚未安装
    // 的 watch，且 inotify 不补发已错过的边沿，导致永久丢失 → 随机超时。
    // 故先轮询 watched() 确认子目录 watch 已就绪，再创建文件。
    const std::string subNorm = Norm(sub);
    const bool armed = WaitFor(
        [&]() {
            const auto watched = w.watched();
            for (const auto& s : watched) {
                if (s == subNorm) return true;
            }
            return false;
        },
        std::chrono::milliseconds(5000));
    ASSERT_TRUE(armed) << "新建子目录的 inotify watch 未在期限内就绪：" << subNorm;

    const fs::path b = sub / "b.txt";
    {
        std::ofstream ofs(b, std::ios::binary | std::ios::trunc);
        ofs << "subfile";
    }

    const std::string bNorm = Norm(b);
    const bool ok = WaitFor(
        [&]() {
            return HasEventIn(bNorm, {docseek::WatchEvent::Created,
                                      docseek::WatchEvent::Modified});
        },
        std::chrono::milliseconds(8000));
    EXPECT_TRUE(ok) << "未在期限内观察到 sub/b.txt 的事件（递归监控失败）";
}

// 移除监控：remove 返回 true，watched() 为空
TEST_F(WatcherTest, RemoveWatch) {
    docseek::Watcher w(
        [&](const fs::path&, docseek::WatchEvent) {},
        300);
    ASSERT_TRUE(w.add(dir_));
    ASSERT_TRUE(w.remove(dir_));
    EXPECT_TRUE(w.watched().empty());
}

#endif  // __linux__
