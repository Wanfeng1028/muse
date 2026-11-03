# DocSeek v0.9 Office 文档文本提取选型决策记录

- 状态：已采用
- 决策范围：.docx/.xlsx/.pptx 文本提取
- 许可基线：DocSeek 仓库为 MIT，Copyright 2026 晚风
- 关联结论：沿用 v0.8 PDF 选型中“避免许可污染”的约束

## 1. 背景与目标

OOXML（Office Open XML）的 .docx/.xlsx/.pptx 本质上是 ZIP 包加 XML：
外层是 ZIP 容器，内部是若干 XML 部件与资源文件。DocSeek 的目标不是渲染版式，
也不是完整实现 OOXML 对象模型，而是稳定抽取可索引的纯文本，供检索使用。

因此核心问题被压缩为两类能力：
1. 可靠解包受支持的 ZIP 条目；
2. 解析少数关键 XML 部件并提取文本节点。

对于常见文件，需要覆盖的典型部件包括 word/document.xml、xl/sharedStrings.xml、
xl/worksheets/sheetN.xml、ppt/slides/slideN.xml 等。

## 2. 硬约束：许可与二进制分发

DocSeek 仓库为 MIT 许可证。任何 GPL 代码以静态链接或动态链接方式进入发布产物，
都可能污染整个二进制的许可传播条件。这是 v0.8 PDF 选型已经确立的红线，
v0.9 继续适用：不允许为了读取 Office 文档而引入 GPL 链接依赖。

对运行时依赖也需谨慎：即使不发生链接，若要求最终用户安装额外外部程序，
也会影响 Docker、CI 和普通二进制分发的简洁性。许可证判断不构成法律意见。

## 3. 候选路线对比

| 路线 | 定性优点 | 定性缺点 | 许可/依赖风险 | 结论 |
| --- | --- | --- | --- | --- |
| A. 纯自研 zip 解析 + 系统 zlib（已采用） | zip 解析手写：local file header、central directory、EOCD；支持 stored 与 deflated；解压调用系统 zlib；零新增第三方依赖、零 GPL 风险、构建快、部署简单 | 不支持 data descriptor、不支持加密条目、不支持 zip64；异常输入需诚实报错 | 自研代码随仓库 MIT；zlib 官网声明其许可证为 zlib license，描述为 free software license，属 OSI 认可的宽松许可证，与 MIT 兼容 | 采用 |
| B. vendoring miniz | 单文件库，集成路径短 | 约 5000 行第三方代码进入仓库，长期维护与审计负担增加 | 社区常描述为 MIT/公共域；未引入前不将具体副本许可结论作为事实（未核验） | 不采用 |
| C. 子进程调用 unzip/7z | 延续 v0.8 PDF 子进程路线，编译期不新增库 | 运行时依赖外部程序，unzip 并非所有发行版预装，Docker 镜像需额外装包；进程开销大；错误信息难结构化 | 不链接第三方库，但外部程序许可与分发策略需单独评估（未核验） | 不采用 |
| D. 子进程调用 libreoffice | 作为办公套件可处理较多办公格式 | 依赖极重，体积数百 MB 级；Docker/CI 不友好；启动慢，超出文本提取需求 | 运行时组件庞大，分发与安装成本高，不适合最小部署 | 不采用 |
| E. 链接 libzip/libxlsxwriter 等 C/C++ 库 | 库成熟，接口完整 | libzip 需要构建依赖；libxlsxwriter 等面向写场景，不适合本读路径；整体功能过剩 | 候选描述中 libzip 为 BSD 系许可，但具体版本/文件头未逐字核验（未核验）；仍会增加构建依赖 | 不采用 |

## 4. 决策与理由

采用路线 A：纯自研 ZIP 解析 + 系统 zlib。

理由如下：
- Office 文本提取只需要“解包 + 读几个 XML”，自研解析器约 300 行即可覆盖常见路径；
- 解压部分不重复造轮子，直接使用系统 zlib（通过 find_package(ZLIB) 发现）；
- zlib 官网声明 zlib license 是 free software license，属 OSI 认可的宽松许可证，与 MIT 兼容；
- 符合 DocSeek“最小依赖、最简部署”的信条；
- 与 v0.8“零 GPL 污染”原则保持一致，不给发布产物引入可疑链接依赖；
- 已知不支持场景通过显式错误暴露，而不是静默跳过或引入过重替代方案。

## 5. 明确记录的局限

以下局限在 v0.9 中如实保留，不静默降级：
- 不支持加密 Office 文档：Office 的加密通常不是普通 ZIP 条目加密，而是 Agile 加密等容器级方案，超出本版本范围；
- 不支持 data descriptor：遇到使用 data descriptor 的 ZIP 条目时诚实报错；
- 不支持 zip64：遇到 zip64 结构或超大条目时诚实报错；
- 仅支持 stored 与 deflated 两种常见条目存储方式；
- 本模块只做文本提取，不做 OOXML 校验、渲染或版式还原。

## 6. 测试策略

测试 fixture 由测试内手写 zip 构造器程序生成，条目使用 zlib compress 进行压缩，不依赖仓库外的二进制 fixture 或外部解压工具。

