cmake_minimum_required(VERSION 3.28)

project(docseek VERSION 0.1.0 LANGUAGES C CXX)

# 统一 C++17 标准
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 线程库
find_package(Threads REQUIRED)

# sqlite3 静态库（含 FTS5 支持）
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
target_link_libraries(sqlite3_static PRIVATE
    Threads::Threads
    ${CMAKE_DL_LIBS}
)
if(NOT MSVC)
    target_compile_options(sqlite3_static PRIVATE -O2)
endif()

# 核心静态库：database / indexer / searcher
add_library(docseek_core STATIC
    src/database.cpp
    src/indexer.cpp
    src/searcher.cpp
)
target_include_directories(docseek_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)
target_link_libraries(docseek_core PUBLIC sqlite3_static)
if(NOT MSVC)
    target_compile_options(docseek_core PRIVATE -Wall -Wextra)
endif()

# 命令行可执行文件
add_executable(docseek src/main.cpp)
target_link_libraries(docseek PRIVATE docseek_core)

# 单元测试
include(FetchContent)
FetchContent_Declare(
    googletest
    URL https://github.com/google/googletest/archive/refs/tags/v1.14.0.zip
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

enable_testing()

add_executable(docseek_tests
    tests/test_database.cpp
    tests/test_indexer.cpp
    tests/test_searcher.cpp
)
target_link_libraries(docseek_tests PRIVATE docseek_core gtest_main)

add_test(NAME docseek_tests COMMAND docseek_tests)

# 安装规则
install(TARGETS docseek RUNTIME DESTINATION bin)
