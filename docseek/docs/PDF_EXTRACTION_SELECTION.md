# DocSeek v0.8 PDF 文本提取选型调研

> 本文档为 DocSeek v0.8「PDF 文本提取」功能的选型调研结论。
> 所有 API 名称、版本号、许可协议均以公开文档为准；无法确认的项明确标注「未核验」，不做臆测。
> 本文档不含代码，仅做调研与决策记录。

## 0. 约束与需求回顾

**项目硬约束**
- 语言/构建：C++17 / CMake >= 3.28 / GCC 13.3 / Linux，命名空间 `docseek`。
- 仓库协议：MIT（Copyright 2026 晚风）。**任何 GPL 代码静态/动态链接都会污染整个二进制文件的协议**，这是硬约束。
- 产品信条：最小依赖、最简部署、可脚本化、可常驻。
- 构建机（验收机）现状：2 核 CPU、约 673MB 可用内存、无 root apt（apt 源已坏，只能 curl 下载 .deb/源码本地解压）、curl 出网正常；系统已有 `poppler-utils 24.02.0`（`/usr/bin/pdftotext` 可用）、`libpoppler.so.134` 运行时库（**无 -dev 头文件**）、zlib 开发头（`/usr/include/zlib.h`）。
- Dockerfile：`debian:12-slim` 两阶段构建；运行阶段当前只装 docseek 二进制 + cppjieba 词典。
- GitHub Actions CI：`ubuntu-latest`，可 `apt-get install` 系统包。

**功能需求**
- **F1**：提取 PDF 全文为 UTF-8 文本。
- **F2**：识别加密 PDF，跳过并记 warning（不抛异常、不中断批量索引）。
- **F3**：损坏/非法 PDF 不中断整批索引（单文件失败只记 error）。
- **F4**：能按页提取文本（页号从 1 开始），供「定位到页」。
- **F5**：单元测试可用程序生成的最小合法 PDF 做 fixture（不依赖外部二进制文件）。

## 1. 候选对比总表

评分：★=差 / ★★=一般 / ★★★=可接受 / ★★★★=良好 / ★★★★★=优秀。定性描述优先，不编造精确数字。

| 维度 | poppler-cpp | qpdf | PoDoFo | MuPDF | 子进程 pdftotext | 自研极简解析器 |
|---|---|---|---|---|---|---|
| C++17 兼容性 | ★★★★ 官方 C++ 接口，需核验具体头文件在 24.02 下的可用性 | ★★★★★ 纯 C++ 库，头文件干净 | ★★★★ C++ 库，但 API 版本间变动较大 | ★★★ 主要为 C API，C++ 封装薄 | ★★★★★ 不涉及编译期接口 | ★★★★★ 完全自控 |
| 构建机可构建性 | ★★ 需 `libpoppler-cpp-dev` 头文件；本机无 -dev 且 apt 坏，需 curl 下载 .deb 本地解压，依赖链深 | ★★★★ 可用源码包本地编译，依赖 zlib 已有；2 核 673MB 下可编，耗时可接受 | ★★★ 依赖较多（zlib、freetype、openssl 等），本地编译链长 | ★★★ 源码庞大，编译慢，2 核/673MB 内存吃紧 | ★★★★★ 零编译，运行时直接调用已存在的 `/usr/bin/pdftotext` | ★★★★ 仅依赖 zlib（已有），编译极快 |
| 包大小 / 运行时体积 | ★★ 引入 libpoppler-cpp + 其依赖，体积较大 | ★★★★ 相对轻量 | ★★★ 中等偏大 | ★★★ 中等偏大 | ★★★★★ 体积增量为 0（复用系统 poppler-utils） | ★★★★★ 增量近乎 0 |
| 维护状态（2026） | ★★★★ poppler 26.10.0（2026-10-04 发布），长期活跃（2026-10-16 编排者经 Keenable 已核验） | ★★★★ qpdf 长期活跃；但官方 README 明确声明 "qpdf does not render PDFs or perform text extraction"（2026-10-16 已核验） | ★★★ 1.1.1（2026-08 发布）、1.1.x 为 LTS（2026-10-16 已核验），历史上活跃度有波动 | ★★★★ 活跃（**未核验**） | ★★★★ 跟随 poppler（**未核验**） | ★★★★★ 自维护 |
| License | ★  GPL-2.0-or-later（2026-10-16 已核验）——**静态/动态链接均污染 MIT，与仓库硬约束直接冲突** | ★★★★★ Apache-2.0，MIT 兼容 | ★★★★ LGPLv2+ 或 MPL-2.0（2026-10-16 已核验），动态链接相对可控但仍有约束 | ★★★★ **AGPL-3.0**（2026-10-16 已核验 mupdf.com/license），对 MIT 项目强污染 | ★★★★ poppler 本身 GPL——**若作为运行时外部进程调用，通常视为独立程序，不构成链接**（法律细节需谨慎，见 §3.5） | ★★★★★ 自有 MIT |
| 文本提取质量 | ★★★★★ 成熟，ToUnicode/加密/容错均好 | ★★ 面向结构操作，非文本提取库，需自解析 content stream | ★★★ 可提取，质量视版本 | ★★★★★ 提取质量业界公认优秀 | ★★★★★ 等同 poppler | ★ 仅覆盖简单 PDF |
| 逐页提取（F4） | ★★★★★ 原生按页 API | ★★★ 需自行按页解析 | ★★★★ 支持 | ★★★★★ 支持 | ★★★★★ `pdftotext -f N -l N` | ★★ 需自实现 |
| 加密 PDF 识别（F2） | ★★★★★ 可查询加密状态 | ★★★★★ 可查询 | ★★★★ 可查询 | ★★★★★ 可查询 | ★★★★ 加密 PDF 会报错，可捕获判据 | ★ 需自实现 |
| Docker/CI 友好度 | ★★ 运行镜像需装 libpoppler-cpp 及依赖，`debian:12-slim` 体积膨胀 | ★★★ 需自带/装库 | ★★ 依赖多 | ★★★ 需自带/装库 | ★★★★★ 运行镜像加 `poppler-utils` 即可（CI 上 `apt-get install poppler-utils`） | ★★★★★ 无新增 |

## 2. 逐候选分析

### 2.1 poppler-cpp（libpoppler-cpp-dev 系统包方案）

- **接口**：poppler 提供 C++ 封装层 `poppler-cpp`，头文件形如 `poppler-document.h`、`poppler-page.h`、`poppler-version.h`（**本机实测**：24.02.0 头文件（`poppler/cpp/poppler-document.h` 等）可用，`document::load_from_file` / `create_page` / `page::text()` 链接运行通过（2026-10-16 编排者实测），但 GPL 污染问题不变，仍排除）。典型流程：加载文档 → 遍历 page → `text()` 取该页文本。
- **可构建性**：本机**没有** `libpoppler-cpp-dev` 头文件，且 apt 源损坏，需 `curl` 下载对应 `.deb` 后本地解压头文件与 `.so`。依赖链深（glib、freetype、fontconfig、nss 等），手工拼装风险高。2 核/673MB 下编译 poppler 本体不现实，只能复用系统已有运行时库，但缺头文件导致**当前状态不可直接编译**。
- **License**：poppler 为 GPL-2.0-or-later（2026-10-16 已核验）。**静态或动态链接均会污染 MIT 二进制**，与仓库硬约束直接冲突。这是致命问题。
- **F1/F4**：满足，按页 API 成熟。
- **F2/F3**：满足，可查加密状态、可 try/catch 容错。
- **F5**：测试 fixture 需程序生成的合法 PDF，与库无关，满足。
- **结论**：**排除**。GPL 污染 + 本机缺头文件 + 运行镜像体积膨胀，三重不利。

### 2.2 qpdf（QPDF C++ API，自行解析 content stream 取文本）

- **接口**：qpdf 提供 C++ 类 `QPDF`、`QPDFPageObjectHelper`、`QPDFObjectHandle` 等（**具体类名/方法以实际源码为准，未核验**）。它擅长 PDF 结构操作与加密处理，**本身不是文本提取库**，要取文本需自行解析 content stream、处理字体与 ToUnicode CMap。
- **可构建性**：Apache-2.0，源码可本地编译，依赖 zlib（已有）。2 核/673MB 下编译 qpdf 本体量级可接受（**具体耗时未核验**）。
- **License**：Apache-2.0，**MIT 兼容**。
- **F1/F4**：不直接满足——需自行实现文本提取与分页，工作量大、质量难保证（ToUnicode、CID 字体、CMap 复杂）。
- **F2**：满足，qpdf 可识别加密。
- **F3**：满足，结构解析容错可控。
- **结论**：**不推荐作为主方案**。License 友好、加密识别强，但「自行解析 content stream 取文本」等于把最难的活重做一遍，违背「最小依赖 + 最简部署」之外的「最省实现」诉求。

### 2.3 PoDoFo

- **接口**：C++ PDF 库，可读写文档、遍历页、提取部分文本（**API 以实际版本为准，未核验**）。
- **可构建性**：依赖 zlib、freetype、openssl 等，本地编译链长；2 核/673MB 下构建压力较大。
- **License**：LGPL-2.0+（**以实际源码为准，未核验**）。LGPL 动态链接相对可控，但引入 LGPL 依赖对「最小依赖」信条不利，且需注意合规细节。
- **文本提取质量**：可用但历史上不如 poppler/MuPDF 成熟（**未核验当前版本**）。
- **F1/F4/F2/F3**：基本满足（需核验具体 API）。
- **结论**：**备选但非首选**。功能可行，但依赖重、构建慢、维护活跃度不确定。

### 2.4 MuPDF

- **接口**：主要是 C API（`fz_*`、`pdf_*` 系列），C++ 封装薄（**具体函数名以实际源码为准，未核验**）。
- **可构建性**：源码体量大，2 核/673MB 下编译吃力，可能 OOM 风险。
- **License**：**AGPL-3.0**（**以实际源码为准，未核验**）。AGPL 对 MIT 项目强污染，且商用/分发约束严格。**与仓库硬约束冲突**。
- **文本提取质量**：优秀，业界公认。
- **结论**：**排除**。AGPL 污染是硬伤；即便忽略许可，构建机内存也吃紧。

### 2.5 子进程调用系统 pdftotext（fork/exec 无 shell）

- **接口**：`fork` + `execv/execve` 直接调用 `/usr/bin/pdftotext`，不经过 shell（避免注入）。参数形如 `pdftotext -f <起始页> -l <结束页> -enc UTF-8 <输入> -`（**具体选项以 `pdftotext --help` 实际输出为准，未核验**），从 stdout 读取 UTF-8 文本。
- **可构建性**：**零编译依赖**。构建机已存在 `/usr/bin/pdftotext`（poppler-utils 24.02.0），直接可用。
- **License 关键点**：poppler 为 GPL。但此处是**以独立进程方式调用外部可执行文件**，不与 docseek 二进制静态/动态链接，通常不构成 GPL 意义上的「衍生作品」或「链接」。**这是本方案成立的核心法律前提**，但细节需谨慎（见 §4 风险）。相比直接链接 libpoppler-cpp，进程调用规避了二进制污染问题。
- **文本提取质量**：等同 poppler，ToUnicode/加密/容错均成熟。
- **F1**：满足。
- **F2**：加密 PDF 时 `pdftotext` 以非零退出并输出错误，可据此跳过并记 warning（退出码/错误文案以 B2 实测为准）。
- **F3**：单个文件失败仅捕获退出码，不抛异常、不中断批量。
- **F4**：`-f` / `-l` 支持按页提取（页号 1 起），满足（2026-10-16 本机实测通过）。
- **F5**：测试 fixture 为程序生成的最小合法 PDF，与调用方式无关，满足；测试时可将 `pdftotext` 路径作为可配置项（**具体实现留待编码阶段，本文档不含代码**）。
- **Docker/CI**：运行镜像 `debian:12-slim` 加 `poppler-utils` 即可；CI `ubuntu-latest` 上 `apt-get install poppler-utils`。
- **结论**：**首选**。零编译依赖、复用系统成熟工具、许可风险通过进程隔离规避、体积增量可控、按页与加密识别均满足。

### 2.6 自研极简 PDF 解析器（仅依赖 zlib）

- **接口**：自实现 xref 解析、content stream 解压（FlateDecode）、文本操作符（`Tj`/`TJ` 等）解析、字体 ToUnicode CMap 解析。
- **可构建性**：仅依赖 zlib（已有），编译极快。
- **License**：自有 MIT，无污染。
- **文本提取质量**：**差**。要正确处理 ToUnicode CMap、CID 字体、Type0/TrueType 嵌入、编码差异、损坏容错，工作量巨大且极易出错，与成熟库差距明显。
- **F1/F2/F3/F4**：均需自实现，加密识别、损坏容错、按页提取都要重造，投入产出比极低。
- **结论**：**排除作为主方案**。违背「最小实现成本」，仅适合未来做「无外部依赖」的降级路径时再评估。

## 3. 需求满足矩阵

| 需求 | poppler-cpp | qpdf | PoDoFo | MuPDF | 子进程 pdftotext | 自研 |
|---|---|---|---|---|---|---|
| F1 全文 UTF-8 | ✅ | ⚠️ 需自实现 | ✅ | ✅ | ✅ | ⚠️ 部分 |
| F2 加密识别+warning | ✅ | ✅ | ✅ | ✅ | ✅（退出码判据） | ❌ |
| F3 损坏容错不中断 | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| F4 按页提取(1 起) | ✅ | ⚠️ 需自实现 | ✅ | ✅ | ✅（`-f`/`-l`） | ❌ |
| F5 程序生成 fixture | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| MIT 兼容 | ❌ GPL | ✅ | ⚠️ LGPL | ❌ AGPL | ✅（进程隔离） | ✅ |
| 本机构建机可构建 | ❌ 缺头文件 | ✅ | ⚠️ 依赖重 | ⚠️ 内存紧 | ✅ 已存在 | ✅ |
| 最小依赖/部署 | ❌ | ⚠️ | ❌ | ❌ | ✅ | ✅ |

## 4. 最终推荐

**排序：**
1. **子进程调用系统 `pdftotext`（首选）** —— 零编译依赖、复用系统成熟工具、按页与加密识别满足、进程隔离规避 GPL 链接污染、运行镜像仅加 `poppler-utils`。构建机与 CI 均已具备或可安装。
2. qpdf（备选） —— Apache-2.0 友好、可识别加密，但文本提取需自实现，工作量大。
3. PoDoFo —— 功能可行，但依赖重、构建慢、LGPL 合规需注意。
4. poppler-cpp —— 功能最好，但 GPL 链接污染 + 本机缺头文件，**排除**。
5. MuPDF —— AGPL 污染 + 构建内存压力，**排除**。
6. 自研 —— 投入产出比过低，**排除**。

**风险与回退方案**
- **许可风险**：进程调用 GPL 工具的法律边界需谨慎对待。回退：若合规评估不通过，改走 qpdf（Apache-2.0）自实现文本提取，或评估 PoDoFo（LGPL，动态链接）。
- **运行时依赖风险**：运行镜像/宿主若无 `pdftotext`，功能不可用。回退：启动时探测 `pdftotext` 可执行路径，缺失则禁用 PDF 索引并记 warning；Dockerfile 运行阶段显式安装 `poppler-utils`。
- **退出码/错误文案不稳定**：加密与损坏 PDF 的判据以实测为准，实现阶段需做健壮封装（超时、非零退出、空输出分类处理）。回退：结合 stderr 关键字与退出码双重判据。
- **版本漂移**：poppler 版本变化可能影响 `-f`/`-l`/`-enc` 选项行为。回退：CI 固定 `poppler-utils` 版本，或改用可配置命令行模板。

> 选型结论：DocSeek v0.8 采用子进程调用系统 `pdftotext`（fork/exec，无 shell）实现 PDF 文本提取，以零编译依赖、进程隔离规避 GPL 链接污染，并复用系统成熟工具满足按页提取与加密识别需求。
--- NEW-END ===

## 5. 编排者独立核验记录（2026-10-16）

本节由编排者（非 dpsk）在本机实测 + Keenable 核验后追加，`未核验` 标注以此为准。

| 核验项 | 方法 | 结果 |
|---|---|---|
| poppler 最新版本/维护状态 | Keenable 搜索 poppler.freedesktop.org | 26.10.0，2026-10-04 发布，活跃 |
| poppler license | Keenable 搜索 conda-forge 记录 | GPL-2.0-or-later |
| poppler-cpp 本机编译+运行 | curl 下载 `libpoppler-cpp-dev` / `libpoppler-cpp0t64` 24.02.0 .deb 本地解压，编译 `document::load_from_file` / `create_page(0)` / `page::text()` 测试程序并运行 | 编译零错误、运行成功，2 页 PDF 识别正确，文本提取成功（技术可行，但 GPL 污染仍排除） |
| qpdf 文本提取能力 | Keenable 搜索 qpdf 官方 README | 官方明确 "qpdf does not render PDFs or perform text extraction"——文本提取需手写 content-stream 解析，否决 |
| PoDoFo 版本/维护/license | Keenable 搜索 GitHub releases + 维护者声明 | 1.1.1（2026-08），1.1.x LTS；LGPLv2+ 或 MPL-2.0 |
| MuPDF license | Keenable 搜索 mupdf.com/license | AGPL-3.0（另有商业许可），否决 |
| pdftotext 基础提取 | 本机 `pdftotext -layout -enc UTF-8` 对程序生成的 2 页最小 PDF | 提取成功，页间以 `\f` 分隔 |
| pdftotext 逐页提取 | 本机 `pdftotext -f 2 -l 2` | 仅输出第 2 页，退出码 0 |
| pdftotext 加密识别 | 待 B2：用程序生成的加密 PDF 实测退出码/stderr 判据 | — |

**最终选型（编排者拍板，与 dpsk 推荐一致）**：子进程调用系统 `pdftotext`（poppler-utils 运行时依赖，`fork`+`exec` 不经过 shell）。

