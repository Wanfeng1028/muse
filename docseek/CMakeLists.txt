# DocSeek v2 构建脚本
# 统一契约：C++17 / CMake >= 3.28 / GCC / 命名空间 docseek / 版本 0.2.0
cmake_minimum_required(VERSION 3.28)

project(docseek VERSION 0.4.0 LANGUAGES C CXX)

# 强制 C++17 标准，关闭编译器扩展以保证可移植性
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 线程库（inotify 监控与 HTTP 常驻服务均需多线程支持）
find_package(Threads REQUIRED)

# ---------------------------------------------------------------------------
# zlib：Office 文档（OOXML zip 包）DEFLATE 解压，系统库
# zlib license 为宽松许可证，非 GPL，与项目"零 GPL 污染"原则一致；
# office_extractor.cpp 的 zip 解析器为纯自研，不依赖 miniz 等第三方 zip 库
# ---------------------------------------------------------------------------
find_package(ZLIB REQUIRED)

# ---------------------------------------------------------------------------
# cppjieba：C++ 中文分词（MIT，yanyiwu/cppjieba）
# 版本选择：v5.6.2（5.6.x 稳定系列；若上游缺失该 tag 可改用 v5.6.0，API 一致）
# 纯头文件库，只需 include 路径；词典文件在构建期复制到 build/dict/
# ---------------------------------------------------------------------------
include(FetchContent)
FetchContent_Declare(
  cppjieba
  GIT_REPOSITORY https://github.com/yanyiwu/cppjieba.git
  GIT_TAG v5.6.2
  GIT_SUBMODULES_RECURSE TRUE
)
FetchContent_MakeAvailable(cppjieba)

# ---------------------------------------------------------------------------
# sqlite3_static：静态库，启用 FTS5 全文检索与线程安全模式
# ---------------------------------------------------------------------------
add_library(sqlite3_static STATIC
  third_party/sqlite3/sqlite3.c
)
target_include_directories(sqlite3_static PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/third_party/sqlite3
)
target_compile_definitions(sqlite3_static PUBLIC
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
  src/structural_precision.cpp
  src/http_server.cpp
  src/watcher.cpp
  src/service.cpp
  src/dict.cpp
  src/jieba_tokenizer.cpp
  src/bigram_tokenizer.cpp

  src/query_parser.cpp
  src/synonyms.cpp
  src/token_locate.cpp

  src/passage_ranker.cpp
  src/pdf_extractor.cpp
  src/office_extractor.cpp
  src/locator.cpp
  src/logger.cpp
  src/metrics.cpp
  src/html_extractor.cpp
)
target_include_directories(docseek_core PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/include
  ${CMAKE_CURRENT_BINARY_DIR}/generated
  ${cppjieba_SOURCE_DIR}/include
  ${cppjieba_SOURCE_DIR}/deps/limonp/include
)
target_link_libraries(docseek_core PUBLIC
  sqlite3_static
  ZLIB::ZLIB
)
# 非 MSVC 平台开启告警
if(NOT MSVC)
  target_compile_options(docseek_core PRIVATE -Wall -Wextra)
endif()

# ---------------------------------------------------------------------------
# cppjieba 词典部署：构建期复制到 build/dict/；安装期装到 share/docseek/dict/
# 运行时词典定位见 src/dict.cpp resolveDictDir()：环境变量 DOCSEEK_DICT_DIR
# > 可执行文件 ../share/docseek/dict > 可执行文件同级 dict/ > 编译期默认路径
# ---------------------------------------------------------------------------
add_custom_target(docseek_copy_dict ALL
  COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_CURRENT_BINARY_DIR}/dict"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different
    "${cppjieba_SOURCE_DIR}/dict/jieba.dict.utf8"
    "${cppjieba_SOURCE_DIR}/dict/hmm_model.utf8"
    "${cppjieba_SOURCE_DIR}/dict/idf.utf8"
    "${cppjieba_SOURCE_DIR}/dict/stop_words.utf8"
    "${CMAKE_CURRENT_BINARY_DIR}/dict/"
  COMMENT "复制 cppjieba 词典到构建目录"
)
add_dependencies(docseek_core docseek_copy_dict)
target_compile_definitions(docseek_core PRIVATE
  DOCSEEK_DICT_DIR_DEFAULT="${CMAKE_CURRENT_BINARY_DIR}/dict"
)
install(FILES
  "${cppjieba_SOURCE_DIR}/dict/jieba.dict.utf8"
  "${cppjieba_SOURCE_DIR}/dict/hmm_model.utf8"
  "${cppjieba_SOURCE_DIR}/dict/idf.utf8"
  "${cppjieba_SOURCE_DIR}/dict/stop_words.utf8"
  DESTINATION share/docseek/dict
)

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
  tests/test_structural_precision.cpp
  tests/test_adjacent_probe_v018.cpp
  tests/test_synonyms_v018.cpp
  tests/test_wave5_v0181.cpp
  tests/test_failure_injection.cpp
  tests/test_locate.cpp
  tests/test_http_server.cpp
  tests/test_watcher.cpp
  tests/test_service.cpp
  tests/test_tokenizer.cpp
  tests/test_token_locate.cpp
  tests/test_hybrid.cpp
  tests/test_ops.cpp
  tests/test_html_basic.cpp
  tests/test_html_entities.cpp
  tests/test_html_malformed.cpp
  tests/test_html_charset.cpp
  tests/test_html_perf.cpp
  tests/test_html_integration.cpp
  tests/test_pdf.cpp
  tests/test_office_docx.cpp
  tests/test_office_xlsx.cpp
  tests/test_office_pptx.cpp
  tests/test_office_index.cpp
  tests/test_query_parser.cpp
  tests/test_query_parser_v017.cpp
  tests/test_tokenizer_neologism.cpp
  tests/test_tokenizer_mixed.cpp
  tests/test_tokenizer_number.cpp
  tests/test_tokenizer_punct.cpp
  tests/test_tokenizer_long.cpp
  tests/test_tokenizer_single.cpp
  tests/test_tokenizer_repeat.cpp
  tests/test_tokenizer_trad.cpp
  tests/test_tokenizer_empty.cpp
  tests/test_tokenizer_stopword.cpp
  tests/test_tokenizer_phrase.cpp
  tests/test_tokenizer_deep_v019.cpp
  tests/test_explain_v019.cpp
  tests/test_tokenizer_perf.cpp
  tests/test_v015_substring_recall.cpp
  tests/test_v015_expand_fix_a.cpp
  tests/test_d4_dfdrop.cpp
  tests/test_v022_wordlevel_prune.cpp
  tests/test_v024_overlap_dedup.cpp
  tests/test_v025_title_signal.cpp
  tests/test_v026_rare_term_bonus.cpp
  tests/test_v027_recurrence.cpp
  tests/test_v029_chinese_numeral.cpp
  tests/test_v031_subject_conflict.cpp
  tests/test_v032_consequence.cpp
  tests/test_v015_filler_words.cpp
  tests/test_v015_search_question.cpp
  tests/test_v015_single_token_precision.cpp
  tests/test_v016_b_fix1.cpp
  tests/test_v016_b_cases.cpp
  tests/test_query_understanding_v020.cpp
  tests/test_locate_target.cpp
  tests/test_bigram_tokenizer.cpp
  tests/test_locate_context.cpp
  tests/test_http_contract.cpp
  tests/test_hybrid_r2_weights.cpp
  tests/test_hybrid_r2_matchquery.cpp
  tests/test_hybrid_r2_emptyquery.cpp
  tests/test_hybrid_r2_emptyindex.cpp
  tests/test_hybrid_r2_topk.cpp
  tests/test_hybrid_r2_longquery.cpp
  tests/test_hybrid_r2_orfallback.cpp
  tests/test_hybrid_r2_phraseboost.cpp
  tests/test_hybrid_r2_explain.cpp
  tests/test_hybrid_r2_searchquestion.cpp
  tests/test_hybrid_r2_searchvsq.cpp
  tests/test_hybrid_r2_titleboost0.cpp
  tests/test_hybrid_r2_stopwords.cpp
  tests/test_hybrid_r2_weightsmid.cpp
  tests/test_tokenizer_neologism_r2.cpp
  tests/test_tokenizer_mixed_r2.cpp
  tests/test_tokenizer_punct_r2.cpp
  tests/test_tokenizer_single_r2.cpp
  tests/test_tokenizer_number_r2.cpp
  tests/test_tokenizer_trad_r2.cpp
  tests/test_tokenizer_long_r2.cpp
  tests/test_tokenizer_repeat_r2.cpp
  tests/test_tokenizer_phrase_r2.cpp
  tests/test_tokenizer_english_r2.cpp
  tests/test_bigram_tokenizer_r2.cpp
  tests/test_tokenizer_singleton_r2.cpp
  tests/test_serve_r2_limit.cpp
  tests/test_serve_r2_errparam.cpp
  tests/test_serve_r2_concurrent.cpp
  tests/test_serve_r2_explain.cpp
  tests/test_serve_r2_boost.cpp
  tests/test_serve_r2_snippet.cpp
  tests/test_serve_r2_locate.cpp
  tests/test_serve_r2_locatelimit.cpp
  tests/test_serve_r2_health.cpp
  tests/test_serve_r2_metrics.cpp
  tests/test_locate_r2_precision.cpp
  tests/test_locate_r2_context.cpp
  tests/test_locate_r2_nonsense.cpp
  tests/test_locate_r2_bigdoc.cpp
  tests/test_locate_r2_limit.cpp
  tests/test_locate_r2_matched.cpp
  tests/test_locate_r2_linebase.cpp
  tests/test_locate_r2_punctfail.cpp
  tests/test_locate_r2_multidoc.cpp
  tests/test_ds_tokenizer_deep.cpp
  tests/test_ds_hybrid_deep.cpp
  tests/test_ds_locate_deep.cpp
  tests/test_passage_weighted_deep.cpp
  tests/test_docfrequency_deep.cpp
  tests/test_v021_weighted_regression_deep.cpp
)
target_link_libraries(docseek_tests PRIVATE
  docseek_core
  gtest_main
)
target_compile_definitions(docseek_tests PRIVATE
  DOCSEEK_DICT_DIR_DEFAULT="${CMAKE_CURRENT_BINARY_DIR}/dict"
)
add_dependencies(docseek_tests docseek_copy_dict)

add_test(NAME docseek_tests COMMAND docseek_tests)

# ---------------------------------------------------------------------------
# 安装规则：仅安装可执行文件到 bin 目录
# ---------------------------------------------------------------------------
install(TARGETS docseek RUNTIME DESTINATION bin)
