#pragma once

#include <string>

namespace docseek {

// 解析 cppjieba 词典所在目录。
//
// 查找顺序：
//   1. 环境变量 DOCSEEK_DICT_DIR（非空且目录存在）；
//   2. 可执行文件所在目录的 ../share/docseek/dict（Linux 通过 /proc/self/exe）；
//   3. 可执行文件所在目录的 dict 子目录；
//   4. 编译期 DOCSEEK_DICT_DIR_DEFAULT。
//
// 若全部失败，抛出 std::runtime_error，错误信息列出所有尝试过的路径。
std::string resolveDictDir();

}  // namespace docseek
