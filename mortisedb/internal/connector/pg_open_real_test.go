package connector

import (
	"os"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
)

func TestOpenPG_RealPostgres(t *testing.T) {
	dsn := os.Getenv("MORTISE_TEST_PG_DSN")
	if dsn == "" {
		t.Skipf("跳过：需真实 PG（MORTISE_TEST_PG_DSN 未设置），本沙箱无 PG 环境")
	}

	cfg := config.SourceConfig{
		Name:        "pgmain",
		Type:        "pg",
		Incremental: "column:updated_at",
		Table:       "orders",
		PrimaryKey:  "order_id",
		Options: map[string]string{
			"conn_str":      dsn,
			"cursor_column": "updated_at",
			"batch_size":    "1000",
		},
	}

	src, err := openPG(cfg)
	if err != nil {
		t.Fatalf("openPG 失败: %v", err)
	}
	if _, err := src.Tables(); err != nil {
		_ = src.Close()
		t.Fatalf("Tables 失败: %v", err)
	}
	if err := src.Close(); err != nil {
		t.Fatalf("Close 失败: %v", err)
	}
}
