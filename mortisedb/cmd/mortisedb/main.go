// Package main 是 MortiseDB「榫卯」的命令行入口。
// 提供 init/sync/query/views/serve/status 子命令。
package main

import (
	"context"
	"database/sql"
	"encoding/csv"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"text/tabwriter"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/api"
	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	mortiselog "github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/scheduler"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
	syncpkg "github.com/Wanfeng1028/muse/mortisedb/internal/sync"
	"github.com/Wanfeng1028/muse/mortisedb/internal/views"
)

// 内嵌的示例配置文件内容。
const sampleConfig = `# MortiseDB 配置文件
version: 1
database: "./data/mortise.db"
addr: ":8421"

sources:
  - name: orders_csv
    type: csv
    path: "./sources/orders.csv"
    table: orders
    primary_key: order_id
    incremental: "column:updated_at"

  - name: users_json
    type: json
    path: "./sources/users.json"
    table: users
    primary_key: user_id
    incremental: hash
    options:
      root: "data.users"

views:
  - name: v_orders
    sql: "SELECT order_id, user_id, amount FROM orders WHERE _m_deleted = 0"
    description: "订单视图"

jobs:
  - name: default
    interval: "30s"
    sources: []

sync:
  conflict: priority
  priority:
    - orders_csv
    - users_json
  soft_delete: true
`

// 示例 CSV 内容。
const sampleOrdersCSV = `order_id,user_id,amount,updated_at
1001,u001,99.50,2024-01-01 10:00:00
1002,u002,150.00,2024-01-02 11:30:00
1003,u001,20.75,2024-01-03 09:15:00
1004,u003,320.00,2024-01-04 14:45:00
1005,u002,45.10,2024-01-05 16:20:00
`

// 示例 JSON 内容。
const sampleUsersJSON = `{
  "data": {
    "users": [
      {"user_id": "u001", "name": "张三", "age": 28, "active": true},
      {"user_id": "u002", "name": "李四", "age": 34, "active": false},
      {"user_id": "u003", "name": "王五", "age": 41, "active": true}
    ]
  }
}
`

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}
	cmd := os.Args[1]
	args := os.Args[2:]

	switch cmd {
	case "init":
		runInit(args)
	case "sync":
		runSync(args)
	case "query":
		runQuery(args)
	case "views":
		runViews(args)
	case "serve":
		runServe(args)
	case "status":
		runStatus(args)
	case "help", "-h", "--help":
		printUsage()
	default:
		fmt.Fprintf(os.Stderr, "未知子命令: %s\n", cmd)
		printUsage()
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Println("MortiseDB「榫卯」- 多源数据同步与查询工具")
	fmt.Println()
	fmt.Println("用法: mortisedb <子命令> [参数]")
	fmt.Println()
	fmt.Println("子命令:")
	fmt.Println("  init    生成示例配置、目录与示例数据源")
	fmt.Println("  sync    执行一次同步")
	fmt.Println("  query   执行单条 SQL 查询")
	fmt.Println("  views   视图管理 (list/add/drop)")
	fmt.Println("  serve   启动 HTTP 服务与调度器")
	fmt.Println("  status  打印系统状态")
	fmt.Println("  help    显示帮助")
}

// runInit 初始化项目目录结构。
func runInit(args []string) {
	fs := flag.NewFlagSet("init", flag.ExitOnError)
	force := fs.Bool("force", false, "覆盖已存在的文件")
	_ = fs.Parse(args)

	// 写配置文件
	if _, err := os.Stat("./mortise.yaml"); err == nil && !*force {
		fmt.Println("mortise.yaml 已存在，跳过（使用 --force 覆盖）")
	} else {
		if err := os.WriteFile("./mortise.yaml", []byte(sampleConfig), 0o644); err != nil {
			fmt.Fprintf(os.Stderr, "写入 mortise.yaml 失败: %v\n", err)
			os.Exit(1)
		}
		fmt.Println("已生成 mortise.yaml")
	}

	// 创建目录
	for _, d := range []string{"data", "sources"} {
		if err := os.MkdirAll(d, 0o755); err != nil {
			fmt.Fprintf(os.Stderr, "创建目录 %s 失败: %v\n", d, err)
			os.Exit(1)
		}
	}

	// 写示例 CSV
	csvPath := filepath.Join("sources", "orders.csv")
	if _, err := os.Stat(csvPath); err != nil || *force {
		if err := os.WriteFile(csvPath, []byte(sampleOrdersCSV), 0o644); err != nil {
			fmt.Fprintf(os.Stderr, "写入 %s 失败: %v\n", csvPath, err)
			os.Exit(1)
		}
		fmt.Println("已生成 sources/orders.csv")
	}

	// 写示例 JSON
	jsonPath := filepath.Join("sources", "users.json")
	if _, err := os.Stat(jsonPath); err != nil || *force {
		if err := os.WriteFile(jsonPath, []byte(sampleUsersJSON), 0o644); err != nil {
			fmt.Fprintf(os.Stderr, "写入 %s 失败: %v\n", jsonPath, err)
			os.Exit(1)
		}
		fmt.Println("已生成 sources/users.json")
	}

	fmt.Println()
	fmt.Println("初始化完成。后续步骤:")
	fmt.Println("  1. 编辑 mortise.yaml 配置数据源")
	fmt.Println("  2. 执行 mortisedb sync 同步数据")
	fmt.Println("  3. 执行 mortisedb serve 启动服务（默认 http://localhost:8421）")
}

// runSync 执行一次同步。
func runSync(args []string) {
	fs := flag.NewFlagSet("sync", flag.ExitOnError)
	configPath := fs.String("config", "", "配置文件路径")
	sourceName := fs.String("source", "", "只同步指定源")
	jobName := fs.String("job", "manual", "任务名")
	_ = fs.Parse(args)

	cfg, err := config.Load(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "加载配置失败: %v\n", err)
		os.Exit(1)
	}

	st, err := store.Open(cfg.Database)
	if err != nil {
		fmt.Fprintf(os.Stderr, "打开数据库失败: %v\n", err)
		os.Exit(1)
	}
	defer st.Close()

	if err := st.Migrate(); err != nil {
		fmt.Fprintf(os.Stderr, "迁移失败: %v\n", err)
		os.Exit(1)
	}

	var sources []string
	if *sourceName != "" {
		sources = []string{*sourceName}
	}

	results, err := syncpkg.Sync(cfg, st, sources, *jobName)
	if err != nil {
		fmt.Fprintf(os.Stderr, "同步失败: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("同步完成:")
	for _, ss := range results {
		fmt.Printf("源 [%s]\n", ss.Source)
		tw := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
		fmt.Fprintln(tw, "  表\t新增\t更新\t删除\t跳过\t冲突")
		for _, ts := range ss.Tables {
			fmt.Fprintf(tw, "  %s\t%d\t%d\t%d\t%d\t%d\n",
				ts.Table, ts.Inserted, ts.Updated, ts.Deleted, ts.Skipped, ts.Conflicts)
		}
		tw.Flush()
	}
}

// runQuery 执行单条 SQL 查询。
func runQuery(args []string) {
	fs := flag.NewFlagSet("query", flag.ExitOnError)
	configPath := fs.String("config", "", "配置文件路径")
	_ = fs.Parse(args)

	rest := fs.Args()
	if len(rest) == 0 {
		fmt.Fprintln(os.Stderr, "用法: mortisedb query \"SELECT ...\"")
		os.Exit(1)
	}
	sqlStr := strings.Join(rest, " ")

	cfg, err := config.Load(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "加载配置失败: %v\n", err)
		os.Exit(1)
	}
	st, err := store.Open(cfg.Database)
	if err != nil {
		fmt.Fprintf(os.Stderr, "打开数据库失败: %v\n", err)
		os.Exit(1)
	}
	defer st.Close()

	cols, rows, err := st.Query(sqlStr)
	if err != nil {
		fmt.Fprintf(os.Stderr, "查询失败: %v\n", err)
		os.Exit(1)
	}

	printTable(cols, rows)
}

// printTable 打印对齐的表格。
func printTable(cols []string, rows [][]any) {
	tw := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
	fmt.Fprintln(tw, strings.Join(cols, "\t"))
	for _, r := range rows {
		cells := make([]string, len(r))
		for i, v := range r {
			cells[i] = formatCell(v)
		}
		fmt.Fprintln(tw, strings.Join(cells, "\t"))
	}
	tw.Flush()
	fmt.Printf("(%d 行)\n", len(rows))
}

// formatCell 将任意值转为字符串。
func formatCell(v any) string {
	switch x := v.(type) {
	case nil:
		return "NULL"
	case []byte:
		return string(x)
	default:
		return fmt.Sprintf("%v", x)
	}
}

// runViews 视图管理。
func runViews(args []string) {
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "用法: mortisedb views <list|add|drop> [...]")
		os.Exit(1)
	}
	sub := args[0]
	rest := args[1:]

	fs := flag.NewFlagSet("views", flag.ExitOnError)
	configPath := fs.String("config", "", "配置文件路径")
	// 兼容参数顺序：允许 --config 出现在子命令之后
	_ = fs.Parse(rest)
	rest = fs.Args()

	cfg, err := config.Load(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "加载配置失败: %v\n", err)
		os.Exit(1)
	}
	st, err := store.Open(cfg.Database)
	if err != nil {
		fmt.Fprintf(os.Stderr, "打开数据库失败: %v\n", err)
		os.Exit(1)
	}
	defer st.Close()

	if err := st.Migrate(); err != nil {
		fmt.Fprintf(os.Stderr, "迁移失败: %v\n", err)
		os.Exit(1)
	}

	switch sub {
	case "list":
		list, err := st.ListViews()
		if err != nil {
			fmt.Fprintf(os.Stderr, "列出视图失败: %v\n", err)
			os.Exit(1)
		}
		tw := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
		fmt.Fprintln(tw, "名称\t描述\tSQL")
		for _, v := range list {
			fmt.Fprintf(tw, "%s\t%s\t%s\n", v.Name, v.Description, v.SQL)
		}
		tw.Flush()
	case "add":
		if len(rest) < 3 {
			fmt.Fprintln(os.Stderr, "用法: mortisedb views add <名称> <SQL> <描述>")
			os.Exit(1)
		}
		name, sqlStr, desc := rest[0], rest[1], rest[2]
		if err := views.Add(st, name, sqlStr, desc); err != nil {
			fmt.Fprintf(os.Stderr, "添加视图失败: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("已添加视图 %s\n", name)
	case "drop":
		if len(rest) < 1 {
			fmt.Fprintln(os.Stderr, "用法: mortisedb views drop <名称>")
			os.Exit(1)
		}
		if err := st.DropView(rest[0]); err != nil {
			fmt.Fprintf(os.Stderr, "删除视图失败: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("已删除视图 %s\n", rest[0])
	default:
		fmt.Fprintf(os.Stderr, "未知视图子命令: %s\n", sub)
		os.Exit(1)
	}
}

// runServe 启动 HTTP 服务与调度器。
func runServe(args []string) {
	fs := flag.NewFlagSet("serve", flag.ExitOnError)
	configPath := fs.String("config", "", "配置文件路径")
	_ = fs.Parse(args)

	cfg, err := config.Load(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "加载配置失败: %v\n", err)
		os.Exit(1)
	}
	st, err := store.Open(cfg.Database)
	if err != nil {
		fmt.Fprintf(os.Stderr, "打开数据库失败: %v\n", err)
		os.Exit(1)
	}
	defer st.Close()

	if err := st.Migrate(); err != nil {
		fmt.Fprintf(os.Stderr, "迁移失败: %v\n", err)
		os.Exit(1)
	}

	logger := mortiselog.New(os.Stdout, "info")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sch := scheduler.New(cfg, st, logger)
	sch.Start(ctx)

	handler := api.NewServer(st, cfg, logger)
	srv := &http.Server{
		Addr:    cfg.Addr,
		Handler: handler,
	}

	// 优雅关闭
	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh
		fmt.Println("\n收到退出信号，正在关闭...")
		cancel()
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutdownCancel()
		_ = srv.Shutdown(shutdownCtx)
	}()

	fmt.Printf("MortiseDB 服务启动于 %s\n", cfg.Addr)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		fmt.Fprintf(os.Stderr, "服务错误: %v\n", err)
		os.Exit(1)
	}
	sch.Stop()
	fmt.Println("已停止")
}

// runStatus 打印系统状态。
func runStatus(args []string) {
	fs := flag.NewFlagSet("status", flag.ExitOnError)
	configPath := fs.String("config", "", "配置文件路径")
	_ = fs.Parse(args)

	cfg, err := config.Load(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "加载配置失败: %v\n", err)
		os.Exit(1)
	}
	st, err := store.Open(cfg.Database)
	if err != nil {
		fmt.Fprintf(os.Stderr, "打开数据库失败: %v\n", err)
		os.Exit(1)
	}
	defer st.Close()

	if err := st.Migrate(); err != nil {
		fmt.Fprintf(os.Stderr, "迁移失败: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("=== 数据源 ===")
	for i := range cfg.Sources {
		src := &cfg.Sources[i]
		fmt.Printf("  %s (类型=%s, 路径=%s)\n", src.Name, src.Type, src.Path)
	}

	fmt.Println()
	fmt.Println("=== 表行数 ===")
	tables, err := st.Tables()
	if err != nil {
		fmt.Fprintf(os.Stderr, "列出表失败: %v\n", err)
		os.Exit(1)
	}
	tw := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
	fmt.Fprintln(tw, "  表\t行数")
	for _, t := range tables {
		cnt, err := st.TableCount(t)
		if err != nil {
			fmt.Fprintf(tw, "  %s\t错误: %v\n", t, err)
			continue
		}
		fmt.Fprintf(tw, "  %s\t%d\n", t, cnt)
	}
	tw.Flush()

	fmt.Println()
	fmt.Println("=== 最近 5 次同步 ===")
	runs, err := st.ListRuns(5)
	if err != nil {
		fmt.Fprintf(os.Stderr, "列出运行记录失败: %v\n", err)
	} else {
		tw2 := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
		fmt.Fprintln(tw2, "  ID\t任务\t开始\t结束\t新增\t更新\t删除\t冲突\t错误")
		for _, r := range runs {
			fmt.Fprintf(tw2, "  %d\t%s\t%s\t%s\t%d\t%d\t%d\t%d\t%s\n",
				r.ID, r.Job, r.StartedAt, r.FinishedAt, r.Inserted, r.Updated, r.Deleted, r.Conflicts, r.Error)
		}
		tw2.Flush()
	}

	fmt.Println()
	conflicts, err := st.ListConflicts("pending")
	if err != nil {
		fmt.Fprintf(os.Stderr, "列出冲突失败: %v\n", err)
	} else {
		fmt.Printf("待处理冲突数: %d\n", len(conflicts))
	}
}

// 确保依赖被使用（避免未使用导入告警）
var (
	_ = context.Background
	_ = csv.NewReader
	_ = json.Marshal
	_ = io.Discard
	_ = sort.Strings
	_ = sql.ErrNoRows
	_ = strconv.Itoa
	_ = syscall.SIGINT
	_ = time.Now
)
