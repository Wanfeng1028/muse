// seed-demo 向 second-brain SQLite 库灌入演示数据：
// 55 篇中文笔记（5 领域 × 11 篇）、双链、复习历史与困难标记。
// 可重复运行：已播种则跳过。
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

const markerTitle = "__seed_demo__"

type seedNote struct {
	title string
	body  string
	tags  []string
}

type reviewPlan struct {
	title   string
	grade   int
	daysAgo int
	hard    bool
}

func main() {
	dbPath := flag.String("db", "data/demo.db", "SQLite 数据库路径")
	flag.Parse()

	s, err := store.Open(*dbPath)
	if err != nil {
		log.Fatalf("打开数据库失败: %v", err)
	}
	defer s.Close()

	ctx := context.Background()

	// 幂等检查：查标记笔记
	existing, err := s.ListNotes("", 1000, 0)
	if err != nil {
		log.Fatalf("读取笔记列表失败: %v", err)
	}
	for _, n := range existing {
		if n.Title == markerTitle {
			fmt.Println("已播种，跳过")
			return
		}
	}

	notes := buildNotes()
	titleToID := make(map[string]int64, len(notes))

	for _, n := range notes {
		created, err := s.CreateNoteFor(ctx, store.Note{
			Title: n.title,
			Body:  n.body,
			Tags:  n.tags,
		}, store.DefaultUser)
		if err != nil {
			log.Fatalf("创建笔记 %q 失败: %v", n.title, err)
		}
		titleToID[n.title] = created.ID
	}

	// 复习历史
	for _, rp := range buildReviews() {
		id, ok := titleToID[rp.title]
		if !ok {
			log.Fatalf("复习计划引用不存在的笔记: %q", rp.title)
		}
		day := time.Now().AddDate(0, 0, -rp.daysAgo)
		if _, err := s.RecordReview(ctx, id, rp.grade, day, store.DefaultUser); err != nil {
			log.Fatalf("记录复习 %q 失败: %v", rp.title, err)
		}
		if rp.grade == 0 {
			// 模拟"忘记→重学"：同一天再记一次
			if _, err := s.RecordReview(ctx, id, 3, day, store.DefaultUser); err != nil {
				log.Fatalf("记录重学 %q 失败: %v", rp.title, err)
			}
		}
		if rp.hard {
			if err := s.SetHardMark(id, store.DefaultUser, true); err != nil {
				log.Fatalf("标记困难 %q 失败: %v", rp.title, err)
			}
		}
	}

	// 统计输出
	byDomain := map[string]int{}
	for _, n := range notes {
		byDomain[domainOf(n.title)]++
	}
	domains := []string{"考研数学", "考研英语", "Go 编程", "产品思考", "读书笔记"}
	fmt.Println("== 播种完成 ==")
	for _, d := range domains {
		fmt.Printf("%s: %d 篇\n", d, byDomain[d])
	}

	stt, err := s.Stats()
	if err != nil {
		log.Fatalf("统计失败: %v", err)
	}
	fmt.Printf("笔记数: %d, 双链数: %d\n", stt.Notes, stt.Links)
	fmt.Printf("有复习记录笔记数: %d\n", len(buildReviews()))

	// 写入标记笔记
	if _, err := s.CreateNoteFor(ctx, store.Note{
		Title: markerTitle,
		Body:  fmt.Sprintf("演示数据播种于 %s", time.Now().Format(time.RFC3339)),
		Tags:  []string{"__internal__"},
	}, store.DefaultUser); err != nil {
		log.Fatalf("写入标记笔记失败: %v", err)
	}
}

// domainOf 从标题前缀判断领域。
func domainOf(title string) string {
	prefixes := []string{"考研数学", "考研英语", "Go 编程", "产品思考", "读书笔记"}
	for _, p := range prefixes {
		if len(title) >= len(p) && title[:len(p)] == p {
			return p
		}
	}
	return "其他"
}

func buildNotes() []seedNote {
	return []seedNote{
		// ===== 考研数学（11 篇） =====
		{
			title: "考研数学·知识地图",
			body:  "这份地图把考研数学拆成三块：高数、线代、概率。高数里最吃分的是极限与导数应用、积分技巧、级数与多元微积分；线代抓特征值、二次型、线性方程组解的结构；概率重点在随机变量分布、数字特征、大数定律与参数估计。\n\n复习节奏上，7~9 月打基础，10 月做真题，11 月集中错题。每章配一份错题清单，按错误类型分类：概念混淆、计算失误、方法不熟。\n\n相关：[[考研数学·特征值与特征向量]] [[考研数学·泰勒展开的应用]] [[考研数学·积分中值定理]]",
			tags:  []string{"考研", "数学", "总览"},
		},
		{
			title: "考研数学·特征值与特征向量",
			body:  "定义：若存在非零向量 α 使 Aα = λα，则 λ 为特征值，α 为特征向量。求解走 |A - λI| = 0 特征多项式，再代回解 (A - λI)α = 0。\n\n关键性质：\n1. 迹 = 特征值之和，行列式 = 特征值之积。\n2. 不同特征值对应的特征向量线性无关。\n3. 实对称矩阵必可正交对角化。\n\n常考：判断能否相似对角化，等价于每个特征值的几何重数等于代数重数。\n\n见 [[考研数学·知识地图]] 与 [[考研数学·二次型与正定]]。",
			tags:  []string{"考研", "数学", "线代"},
		},
		{
			title: "考研数学·二次型与正定",
			body:  "二次型 f = x^T A x，A 对称。用正交变换或配方法化标准形。正定判定：所有顺序主子式 > 0，或所有特征值 > 0。\n\n常见陷阱：合同与相似混淆。合同是 C^T A C，要求 C 可逆；相似是 P^{-1} A P。实对称矩阵下两者可同时成立。\n\n练习：给一个含参二次型，问参数取何值时正定——本质是解主子式不等式组。\n\n延伸 [[考研数学·特征值与特征向量]]。",
			tags:  []string{"考研", "数学", "线代"},
		},
		{
			title: "考研数学·泰勒展开的应用",
			body:  "泰勒公式把函数在某点附近写成多项式加余项。常用展开：e^x、sin x、cos x、ln(1+x)、(1+x)^α 到 x^3 项要背熟。\n\n三大用途：\n1. 求极限时替换等价无穷小的高阶版本。\n2. 判断极值：二阶导为零时看更高阶。\n3. 估计误差：拉格朗日余项给上界。\n\n典型题：lim(x→0) (sin x - x)/x^3 = -1/6。用 sin x = x - x^3/6 + o(x^3) 直接得。\n\n回到 [[考研数学·知识地图]]，另见 [[考研数学·积分中值定理]]。",
			tags:  []string{"考研", "数学", "高数"},
		},
		{
			title: "考研数学·积分中值定理",
			body:  "积分中值定理：f 在 [a,b] 连续，则存在 ξ∈[a,b] 使 ∫_a^b f = f(ξ)(b-a)。\n\n推广（加权形式）：若 g 不变号，则存在 ξ 使 ∫ fg = f(ξ)∫g。\n\n用处：证明存在性问题、估计积分范围、配合罗尔定理构造辅助函数。典型手法是令 F(x) = ∫_a^x f，再对 F 用中值定理。\n\n相关 [[考研数学·泰勒展开的应用]]。",
			tags:  []string{"考研", "数学", "高数"},
		},
		{
			title: "考研数学·级数收敛判别",
			body:  "正项级数：比较判别法、比值判别法（达朗贝尔）、根值判别法（柯西）。交错级数用莱布尼茨：单调递减趋于零。\n\n幂级数收敛半径 R = 1/lim|a_{n+1}/a_n|，端点单独讨论。和函数常用逐项求导、逐项积分，把级数凑成已知展开式。\n\n常考：求 ∑ n x^n 的和函数，先求导再积分回。\n\n见 [[考研数学·知识地图]]。",
			tags:  []string{"考研", "数学", "高数"},
		},
		{
			title: "考研数学·多元函数极值",
			body:  "无条件极值：先解 f_x = f_y = 0 求驻点，再用 AC - B^2 判别（A=f_xx, B=f_xy, C=f_yy）。\n\n条件极值：拉格朗日乘数法，构造 L = f + λg，解方程组。注意边界也要单独讨论。\n\n常见坑：驻点不等于极值点，边界上的最值必须算。\n\n配合 [[考研数学·知识地图]] 复习。",
			tags:  []string{"考研", "数学", "高数"},
		},
		{
			title: "考研数学·常微分方程解法",
			body:  "一阶：可分离变量、齐次、一阶线性（常数变易法）。公式：y' + P(x)y = Q(x)，解 y = e^{-∫P}(∫Q e^{∫P} dx + C)。\n\n二阶常系数齐次：特征方程 r^2 + pr + q = 0，按判别式分三种情况。非齐次特解按 f(x) 形式设，指数、多项式、三角函数各有套路。\n\n回到 [[考研数学·知识地图]]。",
			tags:  []string{"考研", "数学", "高数"},
		},
		{
			title: "考研数学·概率论基础",
			body:  "样本空间、事件、条件概率、全概率公式、贝叶斯公式。独立与互斥是两回事：互斥 P(AB)=0，独立 P(AB)=P(A)P(B)。\n\n随机变量：离散用分布律，连续用密度。常见分布：0-1、二项、泊松、均匀、指数、正态。正态标准化 Z = (X-μ)/σ。\n\n见 [[考研数学·知识地图]] 与 [[考研数学·数字特征]]。",
			tags:  []string{"考研", "数学", "概率"},
		},
		{
			title: "考研数学·数字特征",
			body:  "期望 E(X) = Σ x p 或 ∫ x f dx。方差 D(X) = E(X^2) - [E(X)]^2。协方差 Cov(X,Y) = E(XY) - E(X)E(Y)。\n\n性质：D(aX+b) = a^2 D(X)；独立时 D(X+Y) = D(X)+D(Y)；相关系数 ρ ∈ [-1,1]，|ρ|=1 表示线性关系。\n\n典型题：已知 X~N(μ,σ^2)，求 E(|X-μ|)，用标准化加对称性。\n\n关联 [[考研数学·概率论基础]]。",
			tags:  []string{"考研", "数学", "概率"},
		},
		{
			title: "考研数学·大数定律与中心极限定理",
			body:  "切比雪夫不等式：P(|X-E(X)| ≥ ε) ≤ D(X)/ε^2。它给大数定律提供工具。\n\n大数定律：样本均值依概率收敛到期望。中心极限定理：n 大时样本均值近似正态，无论原分布。\n\n应用：估算投掷次数、抽样误差、保险定价。考试里常给 n 让你用正态近似。\n\n回到 [[考研数学·知识地图]]。",
			tags:  []string{"考研", "数学", "概率"},
		},

		// ===== 考研英语（11 篇） =====
		{
			title: "考研英语·词汇与词根地图",
			body:  "词根是背单词的杠杆。常用：\n- spect 看：inspect, prospect, retrospect\n- port 携带：transport, export, portable\n- dict 说：predict, contradict, dictate\n- duc/duct 引导：conduct, induce, produce\n\n前缀定方向：pre- 前，re- 回/再，sub- 下，trans- 跨。后缀定词性：-tion 名词，-ive 形容词，-ize 动词。\n\n组合记：pro(前) + spect(看) = 向前看 = 展望。\n\n延伸 [[考研英语·长难句拆解]] [[考研英语·高频短语搭配]] [[考研英语·阅读题型套路]]。",
			tags:  []string{"考研", "英语", "词汇"},
		},
		{
			title: "考研英语·长难句拆解",
			body:  "拆句三步：找主谓、切从句、理修饰。\n\n例句：The scientist whose research had been funded by a foundation that focused on climate change argued that policy makers should act. \n\n主干：The scientist argued that... \n定语从句1：whose research... 修饰 scientist。\n定语从句2：that focused on climate change 修饰 foundation。\n宾语从句：that policy makers should act。\n\n先抓骨架再挂枝叶，翻译就不会乱。\n\n见 [[考研英语·词汇与词根地图]]。",
			tags:  []string{"考研", "英语", "语法"},
		},
		{
			title: "考研英语·高频短语搭配",
			body:  "常考搭配：\n- account for 解释、占比例\n- in light of 鉴于\n- give rise to 引起\n- be subject to 受制于\n- stem from 源于\n- put forward 提出\n\n这些短语在完形和翻译里反复出现。记忆方法：放进句子里记，别单背。\n\n例如：The decline in sales stems from several factors. 销售下滑源于多个因素。\n\n回到 [[考研英语·词汇与词根地图]]。",
			tags:  []string{"考研", "英语", "词汇"},
		},
		{
			title: "考研英语·阅读题型套路",
			body:  "阅读六题型：主旨、细节、推断、词义、态度、例证。\n\n细节题：定位关键词，回原文找同义替换，答案往往是原文的 paraphrase。\n推断题：不选原文原话，选合理一步推理。\n态度题：看形容词和动词的感情色彩。\n\n错项特征：绝对化（all, never）、偷换概念、无中生有、张冠李戴。\n\n配合 [[考研英语·词汇与词根地图]] 练。",
			tags:  []string{"考研", "英语", "阅读"},
		},
		{
			title: "考研英语·完形填空技巧",
			body:  "完形考逻辑和搭配。先通读抓主旨，再逐空填。\n\n线索来源：\n1. 上下文逻辑词：however, therefore, moreover。\n2. 固定搭配：depend on, consist of。\n3. 语法一致：主谓一致、时态一致。\n\n拿不准的先跳过，最后用排除法。做完回读一遍看是否通顺。\n\n见 [[考研英语·阅读题型套路]]。",
			tags:  []string{"考研", "英语", "完形"},
		},
		{
			title: "考研英语·翻译得分点",
			body:  "英译汉采点给分。得分点：\n1. 定语从句译成前置定语或独立句。\n2. 被动改主动。\n3. 抽象名词具体化。\n4. 代词指代明确。\n\n例：The idea that machines can think has long fascinated researchers. 译：机器能思考这一想法长期吸引着研究者。把同位语从句提前。\n\n回到 [[考研英语·长难句拆解]]。",
			tags:  []string{"考研", "英语", "翻译"},
		},
		{
			title: "考研英语·写作模板与替换词",
			body:  "大作文三段：描述图画、分析原因、给出建议。\n\n替换词提升档次：\n- important → crucial / vital\n- many → a multitude of\n- think → maintain / contend\n- show → demonstrate / illustrate\n\n开头句：As is vividly depicted in the picture, ...\n结尾句：Only by doing so can we ...\n\n见 [[考研英语·词汇与词根地图]]。",
			tags:  []string{"考研", "英语", "写作"},
		},
		{
			title: "考研英语·新题型匹配",
			body:  "新题型三种：七选五、排序、小标题。\n\n七选五：看空格前后句的衔接词和代词。\n排序：先找首段（通常无指代），再靠时间线和逻辑链。\n小标题：抓段落主题句，通常在段首或段尾。\n\n通用原则：重复出现的名词是线索，指代词必须向前找。\n\n关联 [[考研英语·阅读题型套路]]。",
			tags:  []string{"考研", "英语", "新题型"},
		},
		{
			title: "考研英语·真题精读方法",
			body:  "真题至少做三遍：\n第一遍限时模拟，找感觉。\n第二遍逐句精读，查生词、拆长句、翻译全文。\n第三遍看错题，归类错误原因。\n\n精读时把每篇阅读当翻译材料，把生词抄进本子，按词根归类。一周后回头默写。\n\n见 [[考研英语·词汇与词根地图]]。",
			tags:  []string{"考研", "英语", "方法"},
		},
		{
			title: "考研英语·时间分配策略",
			body:  "考试 180 分钟。建议：\n- 小作文 15 分钟\n- 大作文 35 分钟\n- 阅读 70 分钟（每篇 17 分钟）\n- 新题型 15 分钟\n- 翻译 20 分钟\n- 完形 15 分钟\n- 涂卡 10 分钟\n\n阅读别恋战，一道题超 2 分钟就猜一个标记跳过。作文先打草稿再誊写。\n\n回到 [[考研英语·词汇与词根地图]]。",
			tags:  []string{"考研", "英语", "策略"},
		},

		// ===== Go 编程（11 篇） =====
		{
			title: "Go 编程·学习路线图",
			body:  "从语法到工程：\n1. 基础：变量、流程控制、函数、切片 map。\n2. 面向对象：结构体、方法、接口。\n3. 并发：goroutine、channel、select、sync。\n4. 工程：错误处理、测试、context、模块化。\n5. 进阶：反射、泛型、性能剖析。\n\n每阶段配一个小项目练手。接口是 Go 的灵魂，重点理解隐式实现。\n\n延伸 [[Go 编程·goroutine 与 channel]] [[Go 编程·接口与隐式实现]] [[Go 编程·错误处理惯例]]。",
			tags:  []string{"Go", "编程", "路线"},
		},
		{
			title: "Go 编程·goroutine 与 channel",
			body:  "goroutine 是轻量线程，go f() 即可启动。channel 是 goroutine 间通信的管道。\n\n```go\nch := make(chan int, 3)\ngo func() { ch <- 42 }()\nv := <-ch\n```\n\n无缓冲 channel 同步，有缓冲异步。close 表示不再发送，接收方用 v, ok := <-ch 判断。\n\nselect 多路复用：\n```go\nselect {\ncase v := <-ch1:\n    fmt.Println(v)\ncase <-time.After(time.Second):\n    fmt.Println(\"超时\")\n}\n```\n\n见 [[Go 编程·学习路线图]] 与 [[Go 编程·sync 与并发安全]]。",
			tags:  []string{"Go", "并发", "channel"},
		},
		{
			title: "Go 编程·接口与隐式实现",
			body:  "Go 接口是方法集合，类型只要实现全部方法就自动满足接口，无需显式声明。\n\n```go\ntype Speaker interface {\n    Speak() string\n}\n\ntype Dog struct{}\nfunc (d Dog) Speak() string { return \"汪\" }\n\nvar s Speaker = Dog{}\n```\n\n空接口 interface{} 可接任意类型。类型断言 v, ok := x.(T) 安全取具体类型。\n\n小接口优先，如 io.Reader 只有一个方法。\n\n回到 [[Go 编程·学习路线图]]。",
			tags:  []string{"Go", "接口"},
		},
		{
			title: "Go 编程·错误处理惯例",
			body:  "Go 用返回值传错误，不抛异常。惯例：错误作为最后一个返回值，用 if err != nil 检查。\n\n```go\nf, err := os.Open(\"a.txt\")\nif err != nil {\n    return fmt.Errorf(\"打开文件: %w\", err)\n}\ndefer f.Close()\n```\n\n%w 包裹错误，errors.Is / errors.As 解包。自定义错误实现 error 接口即可。\n\n别用 panic 处理业务错误。\n\n见 [[Go 编程·学习路线图]]。",
			tags:  []string{"Go", "错误处理"},
		},
		{
			title: "Go 编程·sync 与并发安全",
			body:  "多个 goroutine 读写共享变量要加锁。\n\n```go\nvar mu sync.Mutex\nvar counter int\n\nmu.Lock()\ncounter++\nmu.Unlock()\n```\n\nsync.WaitGroup 等一组 goroutine 结束：Add、Done、Wait。sync.Once 只执行一次，适合初始化。sync.RWMutex 读多写少时更优。\n\n竞态检测：go test -race 或 go run -race。\n\n回到 [[Go 编程·goroutine 与 channel]]。",
			tags:  []string{"Go", "并发", "sync"},
		},
		{
			title: "Go 编程·context 用法",
			body:  "context 传取消信号、超时、请求范围的值。\n\n```go\nctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)\ndefer cancel()\nselect {\ncase <-ctx.Done():\n    return ctx.Err()\ncase r := <-resultCh:\n    return r\n}\n```\n\n规则：context 作为函数第一个参数，命名 ctx；不存结构体里；cancel 一定要调。\n\n见 [[Go 编程·学习路线图]]。",
			tags:  []string{"Go", "context"},
		},
		{
			title: "Go 编程·切片与 map 陷阱",
			body:  "切片是数组的视图，含指针、长度、容量。append 可能扩容导致新底层数组。\n\n```go\ns := []int{1, 2, 3}\ns2 := s[:2]\ns2 = append(s2, 99) // 可能改到 s[2]\n```\n\nmap 遍历顺序随机，别依赖。并发写 map 会 panic，需加锁或 sync.Map。nil map 可读不可写。\n\n回到 [[Go 编程·学习路线图]]。",
			tags:  []string{"Go", "切片"},
		},
		{
			title: "Go 编程·defer 执行规则",
			body:  "defer 在函数返回前执行，后进先出。参数在 defer 语句处求值。\n\n```go\nfunc f() (n int) {\n    defer func() { n++ }()\n    return 1 // 返回 2\n}\n```\n\n常见用途：关文件、解锁、恢复 panic。recover 只在 defer 里有效。\n\n注意：defer 在循环里会累积，循环体内慎用。\n\n见 [[Go 编程·错误处理惯例]]。",
			tags:  []string{"Go", "defer"},
		},
		{
			title: "Go 编程·测试与基准",
			body:  "测试文件 _test.go，函数 TestXxx(t *testing.T)。\n\n```go\nfunc TestAdd(t *testing.T) {\n    if got := Add(1, 2); got != 3 {\n        t.Errorf(\"Add(1,2)=%d, want 3\", got)\n    }\n}\n```\n\n表驱动测试：用 []struct{in, want} 遍历。基准函数 BenchmarkXxx(b *testing.B)，循环 b.N 次。覆盖率 go test -cover。\n\n回到 [[Go 编程·学习路线图]]。",
			tags:  []string{"Go", "测试"},
		},
		{
			title: "Go 编程·泛型入门",
			body:  "Go 1.18 引入泛型。类型参数用方括号。\n\n```go\nfunc Map[T, U any](s []T, f func(T) U) []U {\n    r := make([]U, len(s))\n    for i, v := range s {\n        r[i] = f(v)\n    }\n    return r\n}\n```\n\n约束用接口定义：type Number interface{ ~int | ~float64 }。~ 表示底层类型。泛型适合容器和算法，别滥用。\n\n见 [[Go 编程·接口与隐式实现]]。",
			tags:  []string{"Go", "泛型"},
		},
		{
			title: "Go 编程·性能剖析 pprof",
			body:  "导入 net/http/pprof 暴露 /debug/pprof。命令行：go tool pprof。\n\n常见手段：\n1. 减少内存分配，用 sync.Pool 复用。\n2. 预分配切片容量 make([]T, 0, n)。\n3. 字符串拼接用 strings.Builder。\n4. 避免接口装箱开销。\n\n基准对比前后，别凭感觉优化。\n\n回到 [[Go 编程·学习路线图]]。",
			tags:  []string{"Go", "性能"},
		},

		// ===== 产品思考（11 篇） =====
		{
			title: "产品思考·索引",
			body:  "把日常的产品想法整理成几条主线：\n1. 需求判断——真需求还是伪需求。\n2. 用户访谈——怎么问出真话。\n3. 数据指标——北极星与护栏。\n4. 优先级——怎么排。\n5. 复盘——怎么从失败里学。\n\n这份索引用来串联散落的笔记，避免每次重新想。\n\n延伸 [[产品思考·需求真伪判断]] [[产品思考·用户访谈提问]] [[产品思考·北极星指标]]。",
			tags:  []string{"产品", "索引"},
		},
		{
			title: "产品思考·需求真伪判断",
			body:  "判断真需求看三点：\n1. 用户是否已经在用笨办法解决。\n2. 是否愿意为此付费或花时间。\n3. 频率：高频小痛点优于低频大痛点。\n\n伪需求特征：用户说\"挺好\"但不用；只有你在兴奋；靠补贴才有人用。\n\n验证方法：先做最小可用方案，看留存。别一上来就做大而全。\n\n见 [[产品思考·索引]]。",
			tags:  []string{"产品", "需求"},
		},
		{
			title: "产品思考·用户访谈提问",
			body:  "访谈原则：问过去不问未来，问行为不问意愿。\n\n好问题：\n- 你上次遇到这个问题是什么时候？\n- 你当时怎么解决的？\n- 花了多久？\n\n坏问题：\n- 如果有这个功能你会用吗？（会得到客套答案）\n- 你觉得这个想法怎么样？（引导性）\n\n记录原话，别急着总结。\n\n回到 [[产品思考·索引]]。",
			tags:  []string{"产品", "访谈"},
		},
		{
			title: "产品思考·北极星指标",
			body:  "北极星指标是唯一能反映产品核心价值增长的数。要满足：可衡量、反映用户价值、能带动长期增长。\n\n例子：\n- 社交：日活跃互动数\n- 电商：复购率\n- 工具：周活跃用户完成核心动作次数\n\n配护栏指标防跑偏，比如留存、投诉率。别只看总量看人均。\n\n见 [[产品思考·索引]]。",
			tags:  []string{"产品", "指标"},
		},
		{
			title: "产品思考·优先级排序",
			body:  "常见框架：\n1. RICE：Reach × Impact × Confidence / Effort。\n2. Kano：基本型、期望型、兴奋型。\n3. 价值-成本矩阵：四象限。\n\n核心原则：先做能验证假设的最小改动，别一次做太多。资源永远不够，砍掉低价值的事比多做更重要。\n\n回到 [[产品思考·索引]]。",
			tags:  []string{"产品", "优先级"},
		},
		{
			title: "产品思考·竞品分析方法",
			body:  "竞品分析不是抄功能，是看对方为什么这么设计。\n\n步骤：\n1. 列出目标竞品，选 3 个足够。\n2. 拆核心流程，走一遍注册到完成主任务。\n3. 记录差异点，问为什么。\n4. 找对方的用户评价，看抱怨。\n\n输出：一张对比表加三条可借鉴结论。\n\n见 [[产品思考·索引]]。",
			tags:  []string{"产品", "竞品"},
		},
		{
			title: "产品思考·MVP 与小步验证",
			body:  "MVP 是最小可行产品，不是半成品。目标是验证核心假设，不是省钱。\n\n做法：\n1. 明确要验证的假设。\n2. 只做支撑该假设的功能。\n3. 定义成功标准（如 7 日留存 > 20%）。\n4. 快速上线，看数据，再决定加码还是转向。\n\n别把 MVP 做成缩水版的全功能。\n\n回到 [[产品思考·索引]]。",
			tags:  []string{"产品", "MVP"},
		},
		{
			title: "产品思考·留存分析",
			body:  "留存是产品健康的体温计。看次日、7 日、30 日留存曲线。\n\n曲线若持续下滑到零，说明没有核心价值。健康产品会趋于平稳，形成\"微笑曲线\"。\n\n提升留存：\n1. 找到\"魔法时刻\"——用户第一次感受到价值的动作。\n2. 优化新手引导直达该动作。\n3. 召回流失用户，但别骚扰。\n\n见 [[产品思考·北极星指标]]。",
			tags:  []string{"产品", "留存"},
		},
		{
			title: "产品思考·需求池管理",
			body:  "需求池是候选需求的集合，不是待办清单。\n\n管理要点：\n1. 每条需求记来源、场景、期望价值。\n2. 定期清理，过期或已解决的删掉。\n3. 打标签，按主题聚合看趋势。\n4. 不做排期，排期在评审时定。\n\n避免：需求池变成垃圾桶，谁都往里扔。\n\n回到 [[产品思考·索引]]。",
			tags:  []string{"产品", "需求"},
		},
		{
			title: "产品思考·发布与灰度",
			body:  "大功能别一次性全量。灰度发布控制风险。\n\n策略：\n1. 内测 → 小比例用户 → 逐步放量。\n2. 按用户 ID 或地域分桶，保证同组体验一致。\n3. 配监控告警，异常自动回滚。\n\n发布前定好回滚方案，别等出事再想。\n\n见 [[产品思考·索引]]。",
			tags:  []string{"产品", "发布"},
		},
		{
			title: "产品思考·复盘方法",
			body:  "复盘四步：回顾目标、评估结果、分析原因、总结规律。\n\n关键：对事不对人，聚焦可控因素。问三个问题：\n1. 当初的假设是什么？\n2. 实际发生了什么？\n3. 差异为什么产生？\n\n输出可执行的改进项，指定负责人和截止时间，否则复盘白做。\n\n回到 [[产品思考·索引]]。",
			tags:  []string{"产品", "复盘"},
		},

		// ===== 读书笔记（11 篇） =====
		{
			title: "读书笔记·书架总览",
			body:  "把读过的书按主题归档：思维方法、编程技术、产品管理三类。\n\n每本书记三样：核心观点（一句话）、触动最大的例子、一个可行动的改变。\n\n书架是活的：定期重读标记，想法变了就更新笔记。\n\n本书架收录的各篇见下方子笔记。",
			tags:  []string{"读书", "索引"},
		},
		{
			title: "考研英语·熟词僻义",
			body:  "背单词最容易被熟悉的词骗。address 不只“地址”，作动词是“处理、应对”；subject 不只“科目”，可作“使遭受”。\n\n真题里见过这么一句：The proposal was tabled. table 作动词不是“摆桌子”，英式英语里是“提交讨论”，美式里却是“搁置”。同一个词，两种相反的意思，只能靠上下文判断。\n\n我的做法：把 [[考研英语·词汇与词根地图]] 里每个高频词的僻义单独列一张卡片，正面写句子，背面写释义，遇到一次记一次。\n\n可行动的改变：每篇阅读精读时，只挑一个熟词，查清它在句中的确切意思，抄进卡片，不求多。",
			tags:  []string{"考研英语", "词汇"},
		},
		{
			title: "读书笔记·《穷查理宝典》摘抄",
			body:  "核心观点：用多元思维模型看问题，只拿一把锤子的人，看什么都像钉子。\n\n触动的例子：芒格讲可口可乐的投资逻辑，不从财务数字切入，而是从心理学、生物学、数学几路一起推——糖分、咖啡因、条件反射、社会认同，几条线交汇才得出那个结论。\n\n可行动的改变：做决策前，强迫自己至少换两个学科的视角再下判断。比如判断一个需求值不值得做，不光算收益，也想想用户会不会因为“别人都在用”而跟风。\n\n这类跨学科的笔记，都归到 [[读书笔记·书架总览]] 里统一维护。",
			tags:  []string{"读书", "思维"},
		},
		{
			title: "读书笔记·《代码整洁之道》实践",
			body:  "核心观点：代码首先是写给人读的，顺便让机器执行。\n\n触动的例子：书里说函数应该短到一眼看完。我照着改过一个 80 行的处理函数，拆成四个小函数后，读的人不用来回滚动，逻辑也自己显出来了。\n\n可行动的改变：命名不用缩写。把 getUserInfoByIDAndType 这类名字砍成 get 时，先在脑子里问一句：三个月后的我还能看懂吗？看不懂就换个名字。\n\n书里的原则和 [[Go 编程·学习路线图]] 里的实践能对上：Go 的 error 显式处理、接口小而定，本质都是让人读起来省力。\n\n笔记整体挂在 [[读书笔记·书架总览]]。",
			tags:  []string{"读书", "编程"},
		},
		{
			title: "读书笔记·《启示录》产品笔记",
			body:  "核心观点：产品经理的产出不是功能，而是决策。\n\n触动的例子：作者说不要问用户“你想要什么”，用户只会描述现状。要观察他们实际怎么做，从行为里反推痛点。书里举了个例子：用户说想要更快的马，真实需求是更快到达。\n\n可行动的改变：写需求文档时，把“用户要什么”和“用户为什么这么要”分成两栏。第二栏写不出来的需求，先别排期。\n\n这本书的框架可以当 [[产品思考·索引]] 里的入门读物，读完再去看具体的分析方法，顺序更顺。\n\n笔记归到 [[读书笔记·书架总览]]。",
			tags:  []string{"读书", "产品"},
		},
		{
			title: "读书笔记·《深入理解计算机系统》要点",
			body:  "核心观点：程序的性能瓶颈，多半藏在你没看过的内存层级里。\n\n触动的例子：书里用矩阵乘法演示缓存的作用。同样的计算量，把循环顺序调一下，因为访问内存的方式变了，速度差出好几倍。代码一行没改逻辑，只是换了遍历顺序。\n\n可行动的改变：写循环遍历二维数据时，尽量按内存里连续的方向访问。这条在 Go 里同样成立，切片的遍历顺序影响缓存命中。\n\n读这本书要有耐心，一章一章来，笔记记在 [[读书笔记·书架总览]] 下。",
			tags:  []string{"读书", "计算机基础"},
		},
		{
			title: "读书笔记·《数学之美》读后感",
			body:  "核心观点：好的数学模型往往简单，复杂的是把它和现实对上。\n\n触动的例子：作者讲搜索引擎怎么判断网页重要性，用的是图的随机游走——用户随机点链接，停在某个页面的概率就是它的权重。数学本身不新鲜，妙的是把它套到网页结构上。\n\n可行动的改变：遇到难问题先想有没有现成的数学结构能对应。特征值、概率、图，这些在 [[考研数学·知识地图]] 里都梳理过，学的时候觉得抽象，用起来才发现是工具。\n\n笔记挂在 [[读书笔记·书架总览]]。",
			tags:  []string{"读书", "数学"},
		},
		{
			title: "读书笔记·《人月神话》摘抄",
			body:  "核心观点：向进度落后的项目增加人手，只会让它更落后。\n\n触动的例子：书里说，新人要花时间学项目、和别人沟通，这些时间老成员也得搭进去。一条沟通路径变成三条，协调成本涨得比人手快。\n\n可行动的改变：项目排期时，把沟通成本单独列一项。团队从三个人加到五个人，不是产能涨 66%，可能只有 30%。\n\n这条经验对小团队尤其重要，和 [[读书笔记·书架总览]] 里其他管理类的笔记放一起看。",
			tags:  []string{"读书", "管理"},
		},
		{
			title: "读书笔记·《非暴力沟通》实践",
			body:  "核心观点：表达分四步——说观察、说感受、说需要、提请求。别把观察和评价混在一起。\n\n触动的例子：书里区分“你总是迟到”和“这周你迟到了三次”。前一句是评价，后一句是观察。评价一出口，对方立刻进入辩解状态，对话就散了。\n\n可行动的改变：和同事讨论问题时，先把“你总是”换成“这几次”。就这一个改动，对话气氛完全不同。\n\n笔记挂在 [[读书笔记·书架总览]]。",
			tags:  []string{"读书", "沟通"},
		},
		{
			title: "读书笔记·《重来》小团队方法",
			body:  "核心观点：小团队的优势是灵活，别用大公司的流程把它拖死。\n\n触动的例子：作者说不要为了想象中的未来提前扩张。产品还没验证，先招一堆人、开一堆会，成本上去了，方向却没定。\n\n可行动的改变：每次想加流程或加人之前，先问一句“现在的问题真的需要它吗”。先把一个想法做出来给用户看，比开三次评审会有用。\n\n这个思路和 [[产品思考·MVP 与小步验证]] 是一回事，笔记都归到 [[读书笔记·书架总览]]。",
			tags:  []string{"读书", "产品"},
		},
		{
			title: "读书笔记·《英文写作手册》笔记",
			body:  "核心观点：好文章是改出来的，不是写出来的。第一稿只管把想法倒出来，改的时候再理结构。\n\n触动的例子：书里讲被动语态要慎用，因为它藏起了动作的发出者。“错误发生了”和“我犯了错”，后者清楚得多。\n\n可行动的改变：写完一段先放一放，回头只做一件事——找被动句，能改主动就改。这个小习惯对考研英语作文同样适用，和 [[考研英语·写作模板与替换词]] 里的替换技巧配着练。\n\n笔记挂在 [[读书笔记·书架总览]]。",
			tags:  []string{"读书", "写作"},
		},
		{
			title: "读书笔记·重读计划",
			body:  "核心观点：书读一遍不够，值得的书要隔一段时间重读，因为你的问题变了，看到的也不一样。\n\n触动的例子：《代码整洁之道》第一遍读只觉得是规则清单，写过一年代码再读，才明白每条规则背后都是维护成本。\n\n可行动的改变：给书架里的书标三档——常读、重读、归档。每季度挑一本常读的翻一遍，只记新冒出来的想法，旧笔记不动，看自己变了没有。\n\n这个计划挂在 [[读书笔记·书架总览]] 下，和其他单本笔记放一起。",
			tags:  []string{"读书", "计划"},
		},
	}
}

// buildReviews 复习计划：20 条，grade 混用 0/3/4/5，5 条标 hard。
// title 必须与 buildNotes 中的标题逐字一致，否则 main 会 log.Fatal。
func buildReviews() []reviewPlan {
	return []reviewPlan{
		{title: "考研数学·特征值与特征向量", grade: 4, daysAgo: 6},
		{title: "考研数学·泰勒展开的应用", grade: 3, daysAgo: 5, hard: true},
		{title: "考研数学·级数收敛判别", grade: 0, daysAgo: 4, hard: true},
		{title: "考研数学·常微分方程解法", grade: 5, daysAgo: 3},
		{title: "考研数学·数字特征", grade: 4, daysAgo: 2},
		{title: "考研数学·二次型与正定", grade: 3, daysAgo: 8, hard: true},
		{title: "考研英语·长难句拆解", grade: 4, daysAgo: 7},
		{title: "考研英语·阅读题型套路", grade: 3, daysAgo: 5},
		{title: "考研英语·高频短语搭配", grade: 0, daysAgo: 3, hard: true},
		{title: "考研英语·写作模板与替换词", grade: 5, daysAgo: 2},
		{title: "考研英语·完形填空技巧", grade: 4, daysAgo: 9},
		{title: "Go 编程·goroutine 与 channel", grade: 5, daysAgo: 6},
		{title: "Go 编程·切片与 map 陷阱", grade: 3, daysAgo: 4, hard: true},
		{title: "Go 编程·context 用法", grade: 4, daysAgo: 3},
		{title: "Go 编程·错误处理惯例", grade: 0, daysAgo: 5},
		{title: "产品思考·北极星指标", grade: 4, daysAgo: 7},
		{title: "产品思考·优先级排序", grade: 3, daysAgo: 4},
		{title: "产品思考·用户访谈提问", grade: 5, daysAgo: 2},
		{title: "读书笔记·书架总览", grade: 4, daysAgo: 1},
		{title: "考研数学·概率论基础", grade: 3, daysAgo: 10},
	}
}
