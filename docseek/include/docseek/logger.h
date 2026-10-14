#pragma once

#include <map>
#include <string>

namespace docseek {

// 日志级别：数值越大越严重
enum class Level { Debug = 0, Info = 1, Warn = 2, Error = 3 };

// 从环境变量 DOCSEEK_LOG_LEVEL 读取级别（debug/info/warn/error，大小写不敏感），
// 非法值或未设置时回退到 info。可重复调用，以最后一次为准。
void setLevelFromEnv();

// 返回当前生效的日志级别
Level currentLevel();

// 生成新的 request_id，格式 r-%06d，从 r-000001 开始，线程安全（原子计数）
std::string newRequestId();

// 设置当前线程的 request_id（thread_local）
void setRequestId(const std::string& id);

// 清除当前线程的 request_id
void clearRequestId();

// 取当前线程的 request_id，未设置返回空串
std::string currentRequestId();

// 输出一条日志到 stderr（严格单行 JSON）
void log(Level lv, const std::string& module, const std::string& msg);

// 带自定义字段的日志输出，所有字段值按字符串写入 JSON
void log(Level lv, const std::string& module, const std::string& msg,
         const std::map<std::string, std::string>& fields);

}  // namespace docseek
