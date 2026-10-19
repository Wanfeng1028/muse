package pgsource

import "testing"

// TestAssertReadOnlySQLHardening 覆盖字面量/注释感知白名单的加固行为：
// 拒绝 WITH 体内 DML、SELECT INTO、危险函数、分号多语句、非 SELECT/WITH 开头；
// 放行字符串/注释/引用标识符里的关键字，以及内部生成的 columnsSQL/primaryKeySQL。
func TestAssertReadOnlySQLHardening(t *testing.T) {
	type tc struct {
		name            string
		sql             string
		wantErrContains string
	}

	rejects := []tc{
		{
			name:            "WITH 体内 DELETE 大小写混杂",
			sql:             "WITH d AS (DELETE FROM users RETURNING *) SELECT * FROM d",
			wantErrContains: "只读",
		},
		{
			name:            "WITH 体内 delete 全小写",
			sql:             "with d as (delete from t returning *) select 1",
			wantErrContains: "只读",
		},
		{
			name:            "WITH 体内 UPDATE 大小写混杂",
			sql:             "WiTh x AS (UpDaTe t SET a=1 RETURNING *) SELECT 1",
			wantErrContains: "只读",
		},
		{
			name:            "多 CTE 第二个为 INSERT",
			sql:             "WITH a AS (SELECT 1), b AS (INSERT INTO t SELECT * FROM a RETURNING *) SELECT * FROM b",
			wantErrContains: "只读",
		},
		{
			name:            "注释分隔关键字的 WITH 体内 DELETE",
			sql:             "WITH/**/d/**/AS/**/(DELETE/**/FROM/**/t)/**/SELECT/**/1",
			wantErrContains: "只读",
		},
		{
			name:            "SELECT INTO 建表",
			sql:             "SELECT * INTO new_table FROM old_table",
			wantErrContains: "只读",
		},
		{
			name:            "select into temp 小写",
			sql:             "select * into temp t2 from t1",
			wantErrContains: "只读",
		},
		{
			name:            "WITH 体内 MERGE",
			sql:             "WITH d AS (MERGE INTO t USING s ON true WHEN MATCHED THEN DELETE) SELECT 1",
			wantErrContains: "只读",
		},
		{
			name:            "pg_sleep 资源耗尽",
			sql:             "select pg_sleep(10)",
			wantErrContains: "只读",
		},
		{
			name:            "PG_SLEEP 空格大写",
			sql:             "SELECT PG_SLEEP ( 5 )",
			wantErrContains: "只读",
		},
		{
			name:            "dblink_exec 危险函数",
			sql:             "SELECT dblink_exec('c', 'DELETE FROM t')",
			wantErrContains: "只读",
		},
		{
			name:            "分号多语句",
			sql:             "SELECT 1; SELECT 2",
			wantErrContains: "只读",
		},
		{
			name:            "非 SELECT/WITH 开头",
			sql:             "DELETE FROM t",
			wantErrContains: "只读",
		},
	}

	allows := []tc{
		{
			name: "SELECT 1",
			sql:  "SELECT 1",
		},
		{
			name: "WITH cte 纯 SELECT",
			sql:  "WITH cte AS (SELECT 1) SELECT * FROM cte",
		},
		{
			name: "WITH RECURSIVE 纯 SELECT",
			sql:  "WITH RECURSIVE r AS (SELECT 1) SELECT * FROM r",
		},
		{
			name: "字符串里的 delete from users",
			sql:  "SELECT 'delete from users'",
		},
		{
			name: "双引号标识符 update",
			sql:  "SELECT \"update\" FROM t",
		},
		{
			name: "块注释里的 DELETE",
			sql:  "/* DELETE */ SELECT 1",
		},
		{
			name: "行注释开头后接 SELECT",
			sql:  "-- UPDATE\nSELECT 1",
		},
		{
			name: "dollar-quoted 里的 DELETE",
			sql:  "SELECT $$DELETE FROM t$$",
		},
		{
			name: "tagged dollar-quoted 里的 UPDATE",
			sql:  "SELECT $body$UPDATE t$body$ FROM t2",
		},
		{
			name: "into 做标识符子串不误杀",
			sql:  "SELECT * FROM t_into",
		},
		{
			name: "into 做列名前缀不误杀",
			sql:  "SELECT intox FROM t",
		},
		{
			name: "前导块注释加换行",
			sql:  "/* 拉取用户表 */\nSELECT * FROM users",
		},
		{
			// 变更：旧行为是拒（strings.Contains 整串找分号），
			// 本轮改为字面量感知，字符串内的分号不再误杀。
			name: "字符串里的分号不再误杀",
			sql:  "select 'a;b'",
		},
		{
			// 内部生成 SQL，必须通过。
			name: "内部 columnsSQL",
			sql:  "SELECT column_name, udt_name FROM information_schema.columns WHERE table_schema='public' AND table_name=$1 ORDER BY ordinal_position",
		},
		{
			// 内部生成 SQL，必须通过（含 'public'/'PRIMARY KEY' 字符串字面量）。
			name: "内部 primaryKeySQL",
			sql:  "SELECT kcu.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema WHERE tc.table_schema='public' AND tc.table_name=$1 AND tc.constraint_type='PRIMARY KEY' ORDER BY kcu.ordinal_position LIMIT 1",
		},
	}

	for _, c := range rejects {
		t.Run("reject/"+c.name, func(t *testing.T) {
			err := AssertReadOnlySQL(c.sql)
			if err == nil {
				t.Fatalf("期望被拒绝，实际通过: %q", c.sql)
			}
			if !contains(err.Error(), c.wantErrContains) {
				t.Fatalf("错误信息应含 %q，实际: %v", c.wantErrContains, err)
			}
		})
	}

	for _, c := range allows {
		t.Run("allow/"+c.name, func(t *testing.T) {
			if err := AssertReadOnlySQL(c.sql); err != nil {
				t.Fatalf("期望通过，实际错误: %v (sql=%q)", err, c.sql)
			}
		})
	}
}

func contains(s, sub string) bool {
	return len(sub) == 0 || (len(s) >= len(sub) && indexOf(s, sub) >= 0)
}

func indexOf(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}
