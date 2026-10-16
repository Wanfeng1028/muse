// Package config 负责加载与校验 MortiseDB 的 YAML 配置。
package config

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// TableMap 描述 sqlite 源中源表到目标表的映射。
type TableMap struct {
	Source     string `yaml:"source"`
	Target     string `yaml:"target"`
	PrimaryKey string `yaml:"primary_key"`
}

// SourceConfig 描述一个数据源。
type SourceConfig struct {
	Name        string            `yaml:"name"`
	Type        string            `yaml:"type"`
	Path        string            `yaml:"path"`
	Table       string            `yaml:"table"`
	PrimaryKey  string            `yaml:"primary_key"`
	Incremental string            `yaml:"incremental"`
	Tables      []TableMap        `yaml:"tables"`
	Options     map[string]string `yaml:"options"`
}

// SyncPolicy 描述同步冲突策略。
type SyncPolicy struct {
	Conflict   string   `yaml:"conflict"`
	Priority   []string `yaml:"priority"`
	SoftDelete bool     `yaml:"soft_delete"`
	BatchSize  int      `yaml:"batch_size"`
}

// ViewConfig 描述一个视图定义。
type ViewConfig struct {
	Name        string             `yaml:"name"`
	SQL         string             `yaml:"sql"`
	Description string             `yaml:"description"`
	Materialize *MaterializeConfig `yaml:"materialize"`
}

// MaterializeConfig 描述视图的物化配置。
type MaterializeConfig struct {
	Enabled bool   `yaml:"enabled"`
	Refresh string `yaml:"refresh"`
}

// materializeNameRe 校验物化视图名称是否为合法标识符。
var materializeNameRe = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)

// JobConfig 描述一个定时同步任务。
type JobConfig struct {
	Name     string   `yaml:"name"`
	Interval string   `yaml:"interval"`
	Sources  []string `yaml:"sources"`
}

// Config 是 MortiseDB 的总配置。
type Config struct {
	Version  int            `yaml:"version"`
	Database string         `yaml:"database"`
	Addr     string         `yaml:"addr"`
	Sources  []SourceConfig `yaml:"sources"`
	Views    []ViewConfig   `yaml:"views"`
	Jobs     []JobConfig    `yaml:"jobs"`
	Sync     SyncPolicy     `yaml:"sync"`
}

// DefaultConfig 返回内置默认配置。
func DefaultConfig() *Config {
	return &Config{
		Version:  1,
		Database: "./data/mortise.db",
		Addr:     ":8421",
		Sync: SyncPolicy{
			Conflict:   "priority",
			SoftDelete: true,
			BatchSize:  5000,
		},
	}
}

// Load 从 path 读取配置。path 为空时使用 ./mortise.yaml。
// 环境变量 MORTISE_DB / MORTISE_ADDR 会覆盖对应字段。
func Load(path string) (*Config, error) {
	if path == "" {
		path = "./mortise.yaml"
	}

	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("读取配置文件失败 %s: %w", path, err)
	}

	cfg := DefaultConfig()
	if err := yaml.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("解析配置文件失败 %s: %w", path, err)
	}

	if v := os.Getenv("MORTISE_DB"); v != "" {
		cfg.Database = v
	}
	if v := os.Getenv("MORTISE_ADDR"); v != "" {
		cfg.Addr = v
	}

	if cfg.Database == "" {
		cfg.Database = "./data/mortise.db"
	}
	if cfg.Addr == "" {
		cfg.Addr = ":8421"
	}

	if err := cfg.validate(); err != nil {
		return nil, err
	}
	return cfg, nil
}

// validate 校验配置的必填字段与枚举合法性。
func (c *Config) validate() error {
	if c.Sync.Conflict == "" {
		c.Sync.Conflict = "priority"
	}
	if c.Sync.Conflict != "priority" && c.Sync.Conflict != "manual" {
		return fmt.Errorf("sync.conflict 非法取值 %q，仅支持 priority|manual", c.Sync.Conflict)
	}
	if c.Sync.BatchSize <= 0 {
		c.Sync.BatchSize = 5000
	}

	seen := make(map[string]bool, len(c.Sources))
	for i := range c.Sources {
		s := &c.Sources[i]
		if strings.TrimSpace(s.Name) == "" {
			return fmt.Errorf("sources[%d].name 不能为空", i)
		}
		if seen[s.Name] {
			return fmt.Errorf("数据源名称重复: %q", s.Name)
		}
		seen[s.Name] = true

		switch s.Type {
		case "sqlite", "csv", "json", "dir":
		default:
			return fmt.Errorf("数据源 %q 的 type 非法: %q", s.Name, s.Type)
		}

		if s.Incremental == "" {
			s.Incremental = "hash"
		}
		if s.Incremental != "hash" && !strings.HasPrefix(s.Incremental, "column:") {
			return fmt.Errorf("数据源 %q 的 incremental 非法: %q（须为 hash 或 column:<列名>）", s.Name, s.Incremental)
		}
		if strings.HasPrefix(s.Incremental, "column:") && strings.TrimPrefix(s.Incremental, "column:") == "" {
			return fmt.Errorf("数据源 %q 的 incremental 缺少列名", s.Name)
		}

		if strings.TrimSpace(s.Path) == "" {
			return fmt.Errorf("数据源 %q 缺少 path", s.Name)
		}

		switch s.Type {
		case "csv", "json", "dir":
			if strings.TrimSpace(s.Table) == "" {
				return fmt.Errorf("数据源 %q (%s) 必须填写 table", s.Name, s.Type)
			}
			if strings.TrimSpace(s.PrimaryKey) == "" {
				return fmt.Errorf("数据源 %q (%s) 必须填写 primary_key", s.Name, s.Type)
			}
		case "sqlite":
			if len(s.Tables) == 0 {
				return fmt.Errorf("数据源 %q (sqlite) 必须填写 tables", s.Name)
			}
			for j, tm := range s.Tables {
				if strings.TrimSpace(tm.Source) == "" {
					return fmt.Errorf("数据源 %q tables[%d].source 不能为空", s.Name, j)
				}
				if strings.TrimSpace(tm.Target) == "" {
					return fmt.Errorf("数据源 %q tables[%d].target 不能为空", s.Name, j)
				}
				if strings.TrimSpace(tm.PrimaryKey) == "" {
					return fmt.Errorf("数据源 %q tables[%d].primary_key 不能为空", s.Name, j)
				}
			}
		}
	}

	viewSeen := make(map[string]bool, len(c.Views))
	for i, v := range c.Views {
		if strings.TrimSpace(v.Name) == "" {
			return fmt.Errorf("views[%d].name 不能为空", i)
		}
		if viewSeen[v.Name] {
			return fmt.Errorf("视图名称重复: %q", v.Name)
		}
		viewSeen[v.Name] = true
		if strings.TrimSpace(v.SQL) == "" {
			return fmt.Errorf("视图 %q 的 sql 不能为空", v.Name)
		}
		// 物化视图声明校验：enabled 为 false 时视为未启用，不做任何校验。
		if v.Materialize != nil && v.Materialize.Enabled {
			if !materializeNameRe.MatchString(v.Name) {
				return fmt.Errorf("视图 %q 启用物化要求名称为合法标识符", v.Name)
			}
			if c.Views[i].Materialize.Refresh == "" {
				c.Views[i].Materialize.Refresh = "on_sync"
			}
			refresh := c.Views[i].Materialize.Refresh
			if refresh != "on_sync" && refresh != "manual" {
				if !strings.HasPrefix(refresh, "interval:") {
					return fmt.Errorf("视图 %q 的 materialize.refresh 非法: %q", v.Name, refresh)
				}
				d, err := time.ParseDuration(strings.TrimPrefix(refresh, "interval:"))
				if err != nil || d <= 0 {
					return fmt.Errorf("视图 %q 的 materialize.refresh 非法: %q", v.Name, refresh)
				}
			}
		}
	}

	jobSeen := make(map[string]bool, len(c.Jobs))
	for i, j := range c.Jobs {
		if strings.TrimSpace(j.Name) == "" {
			return fmt.Errorf("jobs[%d].name 不能为空", i)
		}
		if jobSeen[j.Name] {
			return fmt.Errorf("任务名称重复: %q", j.Name)
		}
		jobSeen[j.Name] = true
		if strings.TrimSpace(j.Interval) == "" {
			return fmt.Errorf("任务 %q 的 interval 不能为空", j.Name)
		}
		for _, sn := range j.Sources {
			if !seen[sn] {
				return fmt.Errorf("任务 %q 引用了不存在的数据源 %q", j.Name, sn)
			}
		}
	}

	return nil
}

// SourceByName 按名称查找数据源，未找到返回 nil。
func (c *Config) SourceByName(name string) *SourceConfig {
	for i := range c.Sources {
		if c.Sources[i].Name == name {
			return &c.Sources[i]
		}
	}
	return nil
}

// CleanPath 返回去除首尾空白后的路径（供调用方使用，避免重复实现）。
func CleanPath(p string) string {
	return filepath.Clean(strings.TrimSpace(p))
}
