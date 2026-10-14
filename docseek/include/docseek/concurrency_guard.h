// include/docseek/concurrency_guard.h
// 并发守卫：限制同时进入临界区的请求数，带超时等待。
// 原实现位于 src/service.cpp 匿名 namespace 内，为便于单元测试搬至此处。
// 逻辑保持不变，仅补充必要的 include 与命名空间封装。
#pragma once

#include <chrono>
#include <condition_variable>
#include <mutex>

namespace docseek {

// 并发守卫：限制同时进入临界区的请求数，带超时等待。
// 用于 /api/locate 限流：超时拿不到槽位时返回 false，调用方回 429。
class ConcurrencyGuard {
public:
    explicit ConcurrencyGuard(int maxConcurrent)
        : max_(maxConcurrent > 0 ? maxConcurrent : 1) {}

    // 禁用拷贝：守卫持有互斥量与条件变量，不可复制。
    ConcurrencyGuard(const ConcurrencyGuard&) = delete;
    ConcurrencyGuard& operator=(const ConcurrencyGuard&) = delete;

    // 最多等待 timeoutMs 毫秒获取槽位；成功 true，超时 false
    bool tryAcquire(int timeoutMs) {
        std::unique_lock<std::mutex> lk(mutex_);
        auto deadline =
            std::chrono::steady_clock::now() + std::chrono::milliseconds(timeoutMs);
        while (used_ >= max_) {
            if (cv_.wait_until(lk, deadline) == std::cv_status::timeout) {
                return false;
            }
        }
        ++used_;
        return true;
    }

    void release() {
        std::lock_guard<std::mutex> lk(mutex_);
        --used_;
        cv_.notify_one();
    }

private:
    int max_;
    int used_ = 0;
    std::mutex mutex_;
    std::condition_variable cv_;
};

// RAII 持有并发槽位，析构时自动释放
class ScopedSlot {
public:
    ScopedSlot(ConcurrencyGuard& g, int timeoutMs)
        : guard_(g), held_(g.tryAcquire(timeoutMs)) {}

    // 禁用拷贝：RAII 槽位不可复制，避免重复释放。
    ScopedSlot(const ScopedSlot&) = delete;
    ScopedSlot& operator=(const ScopedSlot&) = delete;

    ~ScopedSlot() {
        if (held_) guard_.release();
    }
    bool held() const { return held_; }

private:
    ConcurrencyGuard& guard_;
    bool held_;
};

}  // namespace docseek
