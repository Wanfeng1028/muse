"""演示数据种子。

本模块用于在空数据库上生成一套可读性较强的演示数据，方便本地试用与截图。
调用方式：ensure_seed(db_path)。该函数是幂等的：当 feeds 表已有记录时直接返回，
不会重复插入或覆盖用户数据。

演示数据包含两个分组、六个真实站点风格的订阅源，以及每个源四篇中文文章，
发布时间错开在最近七天内，并混合已读/未读与少量星标状态。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta

from feedflow import db as db_module
from feedflow import store


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _feeds_table_nonempty(db_path: str) -> bool:
    if not os.path.exists(db_path):
        return False
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("SELECT COUNT(1) FROM feeds")
        row = cur.fetchone()
        return bool(row and row[0] > 0)
    except sqlite3.Error:
        return False
    finally:
        conn.close()


        conn.close()


FEED_SPECS = [
    {
        "short": "ruanyf",
        "title": "阮一峰的网络日志",
        "site_url": "https://www.ruanyifeng.com",
        "feed_url": "https://www.ruanyifeng.com/blog/atom.xml",
        "folder": "技术博客",
        "description": "每周分享科技动态与编程随笔。",
        "interval": 60,
    },
    {
        "short": "coolshell",
        "title": "酷壳 CoolShell",
        "site_url": "https://coolshell.cn",
        "feed_url": "https://coolshell.cn/feed",
        "folder": "技术博客",
        "description": "陈皓的技术博客，偏底层与工程实践。",
        "interval": 120,
    },
    {
        "short": "sspai",
        "title": "少数派",
        "site_url": "https://sspai.com",
        "feed_url": "https://sspai.com/feed",
        "folder": "技术博客",
        "description": "高效工作，品质生活。",
        "interval": 60,
    },
    {
        "short": "jiqizhixin",
        "title": "机器之心",
        "site_url": "https://www.jiqizhixin.com",
        "feed_url": "https://www.jiqizhixin.com/rss",
        "folder": "科技资讯",
        "description": "专业的人工智能媒体与产业服务平台。",
        "interval": 30,
    },
    {
        "short": "36kr",
        "title": "36氪",
        "site_url": "https://36kr.com",
        "feed_url": "https://36kr.com/feed",
        "folder": "科技资讯",
        "description": "让一部分人先看到未来。",
        "interval": 30,
    },
    {
        "short": "v2ex",
        "title": "V2EX 技术",
        "site_url": "https://www.v2ex.com",
        "feed_url": "https://www.v2ex.com/feed/tab/tech.xml",
        "folder": "科技资讯",
        "description": "V2EX 技术节点最新主题。",
        "interval": 15,
    },
]

ARTICLES = {
    "ruanyf": [
        {
            "title": "科技爱好者周刊（第 289 期）：软件正在变成服务",
            "author": "阮一峰",
            "link": "https://www.ruanyifeng.com/blog/2024/03/weekly-issue-289.html",
            "summary": "本周话题：订阅制让软件的边界逐渐模糊，我们到底在为什么付费。",
            "text": [
                "过去我们买一份软件，装到自己的硬盘上，用多久都行。现在越来越多的软件只提供在线服务，按月或按年付费，停订即失去访问权。",
                "这种转变不只是商业模式的变化，也改变了用户与工具之间的关系。软件不再是一件可以拥有的东西，而更像一段持续履行的合约。",
                "本期周刊收录了若干与此相关的讨论、工具与文章，希望能给读者一点参考。",
            ],
        },
        {
            "title": "为什么我不再轻易推荐 Tailwind CSS",
            "author": "阮一峰",
            "link": "https://www.ruanyifeng.com/blog/2024/03/tailwind-note.html",
            "summary": "工具很强，但它对团队协作和长期维护的影响需要提前想清楚。",
            "text": [
                "Tailwind 把样式写进 class 里，确实能加快小项目的开发速度，尤其在页面结构频繁变动的早期阶段。",
                "但当项目变大、组件变多之后，同样的 class 组合会在很多地方重复出现。如果没有良好的抽象习惯，模板会变得难以阅读。",
                "我的建议不是拒绝它，而是在引入之前先确认团队能接受这种写法，并约定好复用的边界。",
            ],
        },
        {
            "title": "一次让人头疼的 DNS 排障记录",
            "author": "阮一峰",
            "link": "https://www.ruanyifeng.com/blog/2024/03/dns-debug.html",
            "summary": "服务器能 ping 通却打不开网页，问题最终出在一台内网 DNS 上。",
            "text": [
                "同事反馈某台服务器访问外部网站全部超时，但 ping 外网 IP 是正常的，说明链路本身没有断。",
                "逐个排查之后发现，这台机器使用的内网 DNS 服务器缓存了一条错误的解析记录，把目标域名指向了一个不存在的地址。",
                "清掉缓存并修改 DNS 配置后问题解决。记录下来提醒自己：网络故障时先看解析，再看路由。",
            ],
        },
        {
            "title": "读《计算机程序的构造和解释》有感",
            "author": "阮一峰",
            "link": "https://www.ruanyifeng.com/blog/2024/02/sicp-notes.html",
            "summary": "这本老书对抽象和过程的理解，放到今天依然没有过时。",
            "text": [
                "SICP 讲的不是某一门语言的语法，而是如何用程序去描述过程、构造抽象。这一点在任何编程语言里都适用。",
                "书里的习题难度不低，很多需要反复推敲。但正是在推敲的过程中，会慢慢建立对递归、高阶函数与状态的理解。",
                "如果你已经写过一段时间代码，却总觉得缺了点什么，这本书或许值得翻一翻。",
            ],
        },
    ],
    "coolshell": [
        {
            "title": "聊聊分布式系统里的超时设计",
            "author": "陈皓",
            "link": "https://coolshell.cn/articles/2024/timeout.html",
            "summary": "超时不是随手填一个数字，它直接决定系统在故障时的行为。",
            "text": [
                "很多线上事故的根因不是服务挂了，而是某个调用一直没有返回，把上游的线程和连接全部占满。",
                "设计超时需要考虑调用链的层级、下游的实际耗时分布，以及重试带来的放大效应。层层叠加之后，整体等待时间往往远超预期。",
                "一个可用的做法是给整条链路设置一个总预算，再在每一层分配子预算，让最坏情况下的等待时间是可控的。",
            ],
        },
        {
            "title": "为什么我坚持写单元测试",
            "author": "陈皓",
            "link": "https://coolshell.cn/articles/2024/unit-test.html",
            "summary": "测试不是给领导看的，它是你在重构时唯一敢动手的底气。",
            "text": [
                "有人觉得写测试浪费时间，尤其是需求变化快的项目。但恰恰是变化快的项目，更需要测试来兜住回归。",
                "好的单元测试是快的、独立的、可重复的，它不依赖数据库、网络或时间。达到这个标准之后，你才会愿意频繁地运行它。",
                "我个人的习惯是改完一段逻辑先跑一遍测试，再决定要不要提交。这一步能挡掉很多低级错误。",
            ],
        },
        {
            "title": "关于缓存穿透、击穿与雪崩的通俗解释",
            "author": "陈皓",
            "link": "https://coolshell.cn/articles/2024/cache.html",
            "summary": "三个词经常被混着用，其实描述的是三种不同的失效场景。",
            "text": [
                "穿透指的是查询一个根本不存在的键，请求每次都落到数据库上。常见对策是缓存空值或使用布隆过滤器。",
                "击穿指的是某个热点键失效的瞬间，大量请求同时涌向数据库。可以用互斥锁或逻辑过期来缓解。",
                "雪崩指的是大批键在同一时间失效，或者缓存服务整体不可用。给过期时间加随机抖动、做多级缓存都是常见的做法。",
            ],
        },
        {
            "title": "重新认识 HTTP/2 的多路复用",
            "author": "陈皓",
            "link": "https://coolshell.cn/articles/2024/http2.html",
            "summary": "多路复用解决的是队头阻塞，但也引入了新的调优维度。",
            "text": [
                "HTTP/1.1 里每个连接同一时刻只能处理一个请求，浏览器只能靠开多个连接来并发。连接数一多，握手和拥塞控制的成本就上来了。",
                "HTTP/2 在一条连接上跑多个流，请求之间互不阻塞，理论上能显著减少连接数。但流控窗口设得太小，反而会拖慢传输。",
                "实际调优时要结合服务端的并发模型和客户端的网络条件，不能只看纸面参数。",
            ],
        },
    ],
    "sspai": [
        {
            "title": "用 Raycast 替代 Spotlight 的一个月",
            "author": "少数派编辑部",
            "link": "https://sspai.com/post/2024/raycast",
            "summary": "从启动器到剪贴板管理，它把很多零散的小工具收进了一个入口。",
            "text": [
                "最初只是想要一个更快的启动器，用了几天之后发现它的扩展生态才是重点。",
                "剪贴板历史、窗口管理、单位换算、颜色拾取，这些功能原本要装好几个软件，现在一个快捷键就能搞定。",
                "需要提醒的是，扩展装多了之后启动速度会受影响，建议只保留高频使用的几个。",
            ],
        },
        {
            "title": "我的 2024 年数字极简清单",
            "author": "少数派编辑部",
            "link": "https://sspai.com/post/2024/minimal",
            "summary": "减少通知、减少订阅、减少设备，把注意力留给真正重要的事。",
            "text": [
                "第一步是关掉所有非必要的推送。只保留通讯和日程两类，其余一律静音。",
                "第二步是清理订阅。把一年没有打开的会员全部退掉，把 RSS 里长期不读的源删掉。",
                "第三步是减少设备数量。同一类事情只用一个工具，切换的成本比想象中高很多。",
            ],
        },
        {
            "title": "Obsidian 同步方案对比：官方同步、iCloud 与 Git",
            "author": "少数派编辑部",
            "link": "https://sspai.com/post/2024/obsidian-sync",
            "summary": "三种方案各有取舍，选择取决于你对冲突和隐私的容忍度。",
            "text": [
                "官方同步最省心，端到端加密，多端体验一致，代价是价格偏高。",
                "iCloud 在苹果生态内体验不错，但跨平台支持一般，偶尔会出现同步延迟。",
                "Git 方案自由度高，适合有版本管理习惯的用户，缺点是需要自己处理冲突和移动端操作。",
            ],
        },
        {
            "title": "一套适合远程办公的桌面布置",
            "author": "少数派编辑部",
            "link": "https://sspai.com/post/2024/desk-setup",
            "summary": "显示器、灯光和椅子的优先级，比很多人想得要高。",
            "text": [
                "如果只能升级一样东西，我会先换椅子。久坐带来的问题，靠意志力是解决不了的。",
                "其次是显示器。多一块屏幕带来的效率提升，往往比换一台更快的电脑更明显。",
                "最后是灯光。桌面照明要避免直射屏幕，间接光源对眼睛更友好。",
            ],
        },
    ],
    "jiqizhixin": [
        {
            "title": "开源大模型再迎更新，推理成本下降约四成",
            "author": "机器之心",
            "link": "https://www.jiqizhixin.com/articles/2024-03-llm",
            "summary": "新版本在保持效果的同时，对注意力机制做了针对性优化。",
            "text": [
                "该团队在最新发布的技术报告中表示，通过对注意力计算的稀疏化处理，长上下文场景下的显存占用明显降低。",
                "在公开评测集上，新版本与上一代的成绩基本持平，但在单位 token 的推理成本上下降了约四成。",
                "模型权重已按开源协议放出，社区反馈主要集中在长文本任务的实际表现上。",
            ],
        },
        {
            "title": "多模态模型在医疗影像上的初步尝试",
            "author": "机器之心",
            "link": "https://www.jiqizhixin.com/articles/2024-03-med",
            "summary": "研究团队用图文对数据训练模型，在若干筛查任务上做了对照实验。",
            "text": [
                "论文提出了一种将影像报告与图像对齐的训练方式，希望模型能同时理解视觉信息与临床描述。",
                "在几个公开数据集上，模型的辅助诊断准确率相比基线有所提升，但在罕见病例上仍不稳定。",
                "作者强调这属于早期探索，距离临床落地还有很长的路要走。",
            ],
        },
        {
            "title": "智能体框架混战：谁在定义下一代应用形态",
            "author": "机器之心",
            "link": "https://www.jiqizhixin.com/articles/2024-03-agent",
            "summary": "从工具调用到多智能体协作，各家给出了不同的抽象方式。",
            "text": [
                "过去半年里，围绕智能体的开源框架数量增长很快，思路大致分为工作流编排和自主规划两类。",
                "工作流编排更容易调试和复现，适合任务边界清晰的场景；自主规划更灵活，但可控性较差。",
                "目前还没有出现明显占优的方案，生态碎片化可能会持续一段时间。",
            ],
        },
        {
            "title": "一篇论文引发的讨论：评测集是否正在被污染",
            "author": "机器之心",
            "link": "https://www.jiqizhixin.com/articles/2024-03-bench",
            "summary": "有研究者指出，部分公开评测集的内容可能已进入训练数据。",
            "text": [
                "该研究通过改写题目、替换变量等方式构造了同分布的新测试集，发现多个模型的成绩出现下滑。",
                "作者认为，这提示社区需要更严格地管理评测集的公开范围，并建立动态更新的机制。",
                "也有研究者提出不同看法，认为成绩下滑未必全部来自数据泄漏，可能与改写带来的分布偏移有关。",
            ],
        },
    ],
    "36kr": [
        {
            "title": "一家做工业软件的公司，拿到了 B 轮融资",
            "author": "36氪",
            "link": "https://36kr.com/p/2024-industrial-software",
            "summary": "本轮资金将主要用于产品研发和海外市场拓展。",
            "text": [
                "该公司成立于五年前，主要面向制造业客户提供设计仿真类软件，早期以项目制交付为主。",
                "近两年开始转向标准化产品，客单价有所下降，但续费率明显提升。",
                "创始人表示，海外市场对国产工业软件的接受度正在提高，但认证和渠道仍是主要门槛。",
            ],
        },
        {
            "title": "即时零售赛道再起波澜，多家平台调整补贴策略",
            "author": "36氪",
            "link": "https://36kr.com/p/2024-retail",
            "summary": "从无差别补贴转向精细化运营，履约成本成为关键指标。",
            "text": [
                "过去一年里，即时零售的订单量增长明显，但单均履约成本居高不下，成为盈利的主要障碍。",
                "多家平台开始收缩通用补贴，转向会员体系和品类定向优惠，希望提高用户的复购频次。",
                "业内普遍认为，前置仓密度和配送效率将决定下一阶段的竞争格局。",
            ],
        },
        {
            "title": "出海观察：东南亚市场的支付习惯正在变化",
            "author": "36氪",
            "link": "https://36kr.com/p/2024-sea-payment",
            "summary": "电子钱包渗透率提升，但货到付款仍未完全退场。",
            "text": [
                "在印尼和越南等市场，电子钱包的使用率持续上升，年轻用户对线上支付的接受度明显提高。",
                "不过在一些二三线城市，货到付款依然是主流，原因主要是对平台和商家的信任度不足。",
                "对出海团队来说，支付方式的本地化往往比想象中更复杂，需要和多家服务商对接。",
            ],
        },
        {
            "title": "AI 硬件创业的冷与热",
            "author": "36氪",
            "link": "https://36kr.com/p/2024-ai-hardware",
            "summary": "资本热情不减，但产品定义和供应链仍是难点。",
            "text": [
                "过去一年里，主打 AI 能力的消费硬件项目明显增多，形态从音箱、眼镜到随身设备都有。",
                "融资相对容易，但真正把产品做出来并卖出去的公司并不多，供应链管理和成本控制是常见短板。",
                "有投资人认为，这一波机会更可能出现在与具体场景深度结合的产品上，而非通用形态。",
            ],
        },
    ],
    "v2ex": [
        {
            "title": "大家现在用什么工具管理自己的密码？",
            "author": "Livid",
            "link": "https://www.v2ex.com/t/2024/password",
            "summary": "自建还是用商业服务，讨论主要集中在安全性和便利性的取舍上。",
            "text": [
                "楼主表示自己从浏览器自带的管理器迁移到了独立密码工具，想听听大家的方案。",
                "回复里提到最多的是自建方案，理由是可以完全掌控数据，但需要自己负责备份和安全。",
                "也有用户认为商业服务在易用性和多端同步上更成熟，只要开启两步验证就足够。",
            ],
        },
        {
            "title": "30 岁转行做后端，现实吗？",
            "author": "Livid",
            "link": "https://www.v2ex.com/t/2024/career",
            "summary": "帖子里的回复既有鼓励，也有对市场现状的冷静提醒。",
            "text": [
                "楼主此前从事非技术工作，自学了一段时间编程，想知道现在入行是否还有机会。",
                "有回复建议先通过实际项目验证自己的兴趣和能力，而不是只看招聘要求。",
                "也有人提醒，当前初级岗位竞争激烈，转行需要做好长期投入的准备。",
            ],
        },
        {
            "title": "自建 RSS 阅读器的人，现在还在坚持吗？",
            "author": "Livid",
            "link": "https://www.v2ex.com/t/2024/rss",
            "summary": "从 Google Reader 关闭聊到现在的自托管方案。",
            "text": [
                "楼主说自己用自建阅读器已经好几年，最近在考虑要不要换回商业服务。",
                "回复里不少人表示自建的核心价值在于数据归属和可定制性，尤其是过滤和全文抓取。",
                "也有用户坦言，维护成本确实不低，偶尔会因为抓取失败或数据库问题花上半天时间。",
            ],
        },
        {
            "title": "有没有人用 Rust 写过生产环境的服务？",
            "author": "Livid",
            "link": "https://www.v2ex.com/t/2024/rust",
            "summary": "讨论集中在学习曲线、编译时间和团队协作上。",
            "text": [
                "楼主想了解在实际项目中落地 Rust 的体验，尤其是和现有技术栈的配合。",
                "有回复表示，Rust 在性能和内存安全上的优势明显，但编译时间在大型项目中会比较明显。",
                "也有人提到，团队引入新语言的最大阻力往往不是技术本身，而是招聘和知识传递。",
            ],
        },
    ],
}




def _seed_articles(db_path: str, feed_id: int, short: str, base_time: datetime) -> list[int]:
    """插入演示文章，返回文章 id 列表。"""
    ids: list[int] = []
    for idx, item in enumerate(ARTICLES[short]):
        guid = f"demo-{short}-{idx + 1}"
        published = base_time - timedelta(hours=idx * 6 + (abs(hash(short)) % 5))
        paragraphs = item["text"]
        content_text = "\n\n".join(paragraphs)
        content_html = "".join(f"<p>{p}</p>" for p in paragraphs)
        article_id = store.insert_article(
            db_path,
            feed_id,
            guid,
            item["title"],
            item["author"],
            item["link"],
            item["summary"],
            content_html,
            content_text,
            published.replace(microsecond=0).isoformat(),
        )
        ids.append(article_id)
    return ids


def ensure_seed(db_path: str) -> None:
    """在空数据库上写入演示数据。feeds 表非空时直接返回。"""
    if _feeds_table_nonempty(db_path):
        return

    now_iso = _now_iso()
    # 第一步：分组与订阅源（一个事务提交，避免与后续写操作锁冲突）
    conn = db_module.get_conn(db_path)
    try:
        folder_ids: dict[str, int] = {}
        for pos, name in enumerate(("技术博客", "科技资讯")):
            cur = conn.execute(
                "INSERT INTO folders (name, position, created_at) VALUES (?, ?, ?)",
                (name, pos, now_iso),
            )
            folder_ids[name] = cur.lastrowid

        feed_ids: dict[str, int] = {}
        for spec in FEED_SPECS:
            # feed_url 有 UNIQUE 约束，直接插入天然去重
            cur = conn.execute(
                """INSERT OR IGNORE INTO feeds (
                    folder_id, title, site_url, feed_url, description,
                    interval_min, enabled, last_fetched_at, last_status,
                    last_error, etag, modified, position, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, 'ok', '', '', '', 0, ?)""",
                (
                    folder_ids[spec["folder"]],
                    spec["title"],
                    spec["site_url"],
                    spec["feed_url"],
                    spec["description"],
                    spec["interval"],
                    now_iso,
                    now_iso,
                ),
            )
            feed_id = cur.lastrowid
            if not feed_id:
                row = conn.execute(
                    "SELECT id FROM feeds WHERE feed_url = ?", (spec["feed_url"],)
                ).fetchone()
                feed_id = row[0]
            feed_ids[spec["short"]] = feed_id
        conn.commit()
    finally:
        conn.close()

    # 第二步：文章（store.insert_article 自带连接与 FTS 触发器同步）
    starred_ids: list[int] = []
    base_time = datetime.now(UTC) - timedelta(hours=3)
    for spec in FEED_SPECS:
        ids = _seed_articles(db_path, feed_ids[spec["short"]], spec["short"], base_time)
        # 每个源第 2 篇加星标
        if len(ids) >= 2:
            starred_ids.append(ids[1])

    # 文章状态用 store 接口设置（article_id 为准）
    for article_id in starred_ids:
        store.set_starred(db_path, article_id, 1)
    # 约 1/3 标为已读：按 id 排序每 3 篇标 1 篇
    conn = db_module.get_conn(db_path)
    try:
        rows = conn.execute("SELECT id FROM articles ORDER BY id").fetchall()
    finally:
        conn.close()
    for i, row in enumerate(rows):
        if i % 3 == 0:
            store.set_read(db_path, row[0], 1)
