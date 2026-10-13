# DocSeek v2 构建脚本
# 统一契约：C++17 / CMake >= 3.28 / GCC / 命名空间 docseek / 版本 0.2.0
cmake_minimum_required(VERSION 3.28)

project(docseek VERSION 0.2.0 LANGUAGES C CXX)

# 强制 C++17 标准，关闭编译器扩展以保证可移植性
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 线程库（inotify 监控与 HTTP 常驻服务均需多线程支持）
find_package(Threads REQUIRED)

# ---------------------------------------------------------------------------
# sqlite3_static：静态库，启用 FTS5 全文检索与线程安全模式
# ---------------------------------------------------------------------------
add_library(sqlite3_static STATIC
  third_party/sqlite3/sqlite3.c
)
target_include_directories(sqlite3_static PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/third_party/sqlite3
)
target_compile_definitions(sqlite3_static PRIVATE
  SQLITE_ENABLE_FTS5
  SQLITE_THREADSAFE=1
)
target_link_libraries(sqlite3_static PUBLIC
  Threads::Threads
  ${CMAKE_DL_LIBS}
)
# 非 MSVC 平台（本工程面向 GCC）追加 -O2 优化
if(NOT MSVC)
  target_compile_options(sqlite3_static PRIVATE -O2)
endif()

# ---------------------------------------------------------------------------
# web_ui.h 生成：将 web/index.html 内嵌为 C++ 字符串常量
# 硬约束：index.html 全文不允许出现 "${" 序列，否则会被 CMake 误解析
# ---------------------------------------------------------------------------
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/web/index.html" _WEB_HTML)
# 反斜杠转义：单反斜杠 -> 双反斜杠
string(REPLACE "\\" "\\\\" _WEB_HTML "${_WEB_HTML}")
# 双引号转义：双引号 -> 反斜杠 + 双引号
string(REPLACE "\"" "\\\"" _WEB_HTML "${_WEB_HTML}")
# 换行处理：换行 -> \n" + 换行 + "（利用 C++ 相邻字符串字面量拼接）
string(REPLACE "\n" "\\n\"\n\"" _WEB_HTML "${_WEB_HTML}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/generated/web_ui.h"
  "#pragma once\nnamespace docseek {\ninline constexpr const char* kWebUiHtml =\n\"${_WEB_HTML}\";\n}  // namespace docseek\n")

# ---------------------------------------------------------------------------
# docseek_core：核心静态库，包含全部业务逻辑（数据库/索引/检索/HTTP/监控/服务）
# ---------------------------------------------------------------------------
add_library(docseek_core STATIC
  src/database.cpp
  src/indexer.cpp
  src/searcher.cpp
  src/http_server.cpp
  src/watcher.cpp
  src/service.cpp
)
target_include_directories(docseek_core PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/include
  ${CMAKE_CURRENT_BINARY_DIR}/generated
)
target_link_libraries(docseek_core PUBLIC
  sqlite3_static
)
# 非 MSVC 平台开启告警
if(NOT MSVC)
  target_compile_options(docseek_core PRIVATE -Wall -Wextra)
endif()

# ---------------------------------------------------------------------------
# docseek：命令行可执行文件（index / search / stats / prune / serve / help / version）
# ---------------------------------------------------------------------------
add_executable(docseek
  src/main.cpp
)
target_link_libraries(docseek PRIVATE
  docseek_core
)

# ---------------------------------------------------------------------------
# 测试：使用 googletest v1.14.0，通过 FetchContent 拉取（与 v1 保持一致）
# ---------------------------------------------------------------------------
include(FetchContent)
enable_testing()

FetchContent_Declare(
  googletest
  URL https://github.com/google/googletest/archive/refs/tags/v1.14.0.zip
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
# Windows 平台避免覆盖父工程的运行库配置（此处保留以兼容跨平台）
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

add_executable(docseek_tests
  tests/test_database.cpp
  tests/test_indexer.cpp
  tests/test_searcher.cpp
  tests/test_http_server.cpp
  tests/test_watcher.cpp
  tests/test_service.cpp
)
target_link_libraries(docseek_tests PRIVATE
  docseek_core
  gtest_main
)

add_test(NAME docseek_tests COMMAND docseek_tests)

# ---------------------------------------------------------------------------
# 安装规则：仅安装可执行文件到 bin 目录
# ---------------------------------------------------------------------------
install(TARGETS docseek RUNTIME DESTINATION bin)
