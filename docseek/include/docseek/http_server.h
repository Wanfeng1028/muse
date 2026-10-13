#pragma once

#include <functional>
#include <map>
#include <string>

namespace docseek {

// HTTP 请求结构：method 为 "GET"/"POST"/"DELETE"，path 为 URL 解码后的路径（不含 query），
// headers 的 key 全部小写，query 为解析后的查询参数键值对。
struct HttpRequest {
  std::string method;                                 // 请求方法（大写）
  std::string target;                                 // 原始请求目标（含 query）
  std::string path;                                   // URL 解码后的路径（不含 query）
  std::map<std::string, std::string> query;           // 查询参数
  std::map<std::string, std::string> headers;         // 请求头，key 全小写
  std::string body;                                   // 请求体
};

// HTTP 响应结构：包含状态码、Content-Type 与响应体，并提供若干常用构造辅助。
struct HttpResponse {
  int status = 200;                                                    // HTTP 状态码
  std::string content_type = "application/json; charset=utf-8";        // 默认 JSON 内容类型
  std::string body;                                                    // 响应体

  // 构造 JSON 响应（默认状态码 200）。
  static HttpResponse json(const std::string& body, int status = 200);
  // 构造 HTML 文本响应（content_type=text/html; charset=utf-8）。
  static HttpResponse text(const std::string& body, int status = 200);
  // 构造错误响应，body 为 {"error":"msg"} 形式。
  static HttpResponse err(int status, const std::string& msg);
};

// 简易 HTTP 常驻服务器：支持注册 GET/POST/DELETE 处理器，启动后监听端口并处理请求。
class HttpServer {
 public:
  // 请求处理器类型：接收请求返回响应。
  using Handler = std::function<HttpResponse(const HttpRequest&)>;

  // 构造服务器对象（不监听端口）。
  HttpServer();
  // 析构时自动停止服务器并释放资源。
  ~HttpServer();

  // 禁止拷贝构造。
  HttpServer(const HttpServer&) = delete;
  // 禁止拷贝赋值。
  HttpServer& operator=(const HttpServer&) = delete;

  // 注册 GET 请求处理器。
  void onGet(const std::string& path, Handler h);
  // 注册 POST 请求处理器。
  void onPost(const std::string& path, Handler h);
  // 注册 DELETE 请求处理器。
  void onDelete(const std::string& path, Handler h);

  // 启动服务器并监听指定端口（port=0 时自动分配端口），失败抛 std::runtime_error。
  void start(int port);
  // 停止服务器并等待后台线程结束，可重复调用。
  void stop();

  // 返回实际监听端口，未启动时返回 -1。
  int port() const;

 private:
  struct Impl;
  Impl* impl_;
};

}  // namespace docseek
