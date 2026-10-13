// include/docseek/watcher.h
#pragma once

#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace docseek {

// 文件变更事件类型：新建、修改、删除
enum class WatchEvent { Created, Modified, Deleted };

// Linux inotify 递归目录监控器，带防抖合并，用于实时增量索引
class Watcher {
 public:
  // 事件回调：path 为绝对规范化路径，event 为变更类型
  using Callback = std::function<void(const std::string& path, WatchEvent event)>;

  // 构造监控器，cb 为事件回调，debounceMs 为防抖窗口毫秒数
  explicit Watcher(Callback cb, int debounceMs = 800);
  // 析构：停止监控线程并释放 inotify 资源
  ~Watcher();
  // 禁止拷贝构造
  Watcher(const Watcher&) = delete;
  // 禁止拷贝赋值
  Watcher& operator=(const Watcher&) = delete;

  // 添加目录监控（递归含子目录），dir 不存在或非目录返回 false，已添加返回 true
  bool add(const std::string& dir);
  // 移除目录监控，不在监控中返回 false
  bool remove(const std::string& dir);
  // 返回当前所有被监控目录的绝对规范化路径列表
  std::vector<std::string> watched() const;

 private:
  struct Impl;                       // 实现细节隐藏（PIMPL）
  std::unique_ptr<Impl> impl_;       // 唯一实现指针
};

}  // namespace docseek
