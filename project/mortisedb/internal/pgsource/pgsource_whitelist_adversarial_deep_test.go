package pgsource

import (
	"strings"
	"testing"
)

func advAllow(t *testing.T, q string) {
	t.Helper()
	if err := AssertReadOnlySQL(q); err != nil {
		t.Errorf("期望允许 %q，实际被拒: %v", q, err)
	}
}

func advReject(t *testing.T, q string) {
	t.Helper()
	if err := AssertReadOnlySQL(q); err == nil {
		t.Errorf("期望拒绝 %q，实际被允许", q)
	}
}

func TestAdvBlockCommentSplitsKeyword(t *testing.T) {
	advReject(t, "SEL/**/ECT 1")
	advReject(t, "SEL/**//*x*/ECT 1")
	advReject(t, "SEL/*c*/ECT * FROM t")
}

func TestAdvLineCommentSplitsKeyword(t *testing.T) {
	advReject(t, "SEL--xxx\nECT 1")
	advReject(t, "SEL--xxx\nECT * FROM t")
}

func TestAdvDollarQuotedBodyHidesDML(t *testing.T) {
	advAllow(t, "SELECT $$ INSERT INTO t VALUES(1) $$")
	advAllow(t, "SELECT $body$ DELETE FROM t $body$")
	advAllow(t, "WITH x AS (SELECT $tag$ update t set a=1 $tag$) SELECT * FROM x")
}

func TestAdvStringLiteralAndQuotedIdentifierNoFalsePositive(t *testing.T) {
	advAllow(t, "SELECT 'insert into t'")
	advAllow(t, `SELECT "update" FROM t`)
	advAllow(t, "SELECT 'delete from t', 'merge'")
	advAllow(t, `SELECT "insert", "delete" FROM t`)
}

func TestAdvWithBodyDMLRejected(t *testing.T) {
	advReject(t, "WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x")
	advReject(t, "WITH x AS (UPDATE t SET a=1 RETURNING *) SELECT * FROM x")
	advReject(t, "WITH x AS (INSERT INTO t VALUES(1) RETURNING *) SELECT * FROM x")
}

func TestAdvSelectIntoRejected(t *testing.T) {
	advReject(t, "SELECT * INTO newt FROM t")
	advReject(t, "SeLeCt * InTo newt FROM t")
	advReject(t, "SELECT INTO newt FROM t")
}

func TestAdvCaseVariantsRejected(t *testing.T) {
	advReject(t, "WITH x AS (SELECT 1) inSeRt INTO t VALUES(1)")
	advReject(t, "SELECT pg_sleep(1)")
	advReject(t, "SELECT PG_SLEEP(1)")
	advReject(t, "SELECT Pg_SlEeP(1)")
}

func TestAdvUnicodeLookalikeRejected(t *testing.T) {
	advReject(t, "SEL\uFF25CT 1")
	advAllow(t, "SELECT\uFF11")
	advReject(t, "\uFF33ELECT 1")
}

func TestAdvSemicolonStackingRejected(t *testing.T) {
	advReject(t, "SELECT 1; SELECT 2")
	advReject(t, "SELECT 1;-- trailing")
	advReject(t, "SELECT 1 ;")
}

func TestAdvDangerousFunctionsRejected(t *testing.T) {
	advReject(t, "SELECT pg_sleep(10)")
	advReject(t, "SELECT pg_sleep /*c*/ (10)")
	advReject(t, "SELECT pg_sleep((select 1))")
	advReject(t, "SELECT pg_terminate_backend(123)")
	advReject(t, "SELECT dblink_exec('x')")
	advReject(t, "SELECT dblink_connect('y')")
	advReject(t, "SELECT pg_cancel_backend(1)")
}

func TestAdvNormalSelectAllowed(t *testing.T) {
	advAllow(t, "SELECT 1")
	advAllow(t, "WITH x AS (SELECT 1) SELECT * FROM x")
	advAllow(t, "  select * from t where a = 'x'  ")
	advAllow(t, "SELECT a, b FROM t ORDER BY a")
}

func TestAdvNonSelectStartRejected(t *testing.T) {
	advReject(t, "DELETE FROM t")
	advReject(t, "")
	advReject(t, "   ")
	advReject(t, "-- only comment")
	advReject(t, "/* only block */")
	advReject(t, "UPDATE t SET a=1")
	advReject(t, "INSERT INTO t VALUES(1)")
}

func TestAdvCommentsHidingDMLAllowed(t *testing.T) {
	advAllow(t, "SELECT 1 /* delete from t */")
	advAllow(t, "SELECT 1 -- delete")
	advAllow(t, "SELECT 1 -- update t set a=1")
}

func TestAdvCommentInsideKeywordCannotBypass(t *testing.T) {
	advReject(t, "SEL/*x*/ECT 1")
	advReject(t, "SEL--x\nECT 1")
	advReject(t, "SEL/**/ECT/**/1")
}

func TestAdvDollarQuoteUnclosedStripped(t *testing.T) {
	advAllow(t, "SELECT $$ insert into t")
	advAllow(t, "SELECT $tag$ delete from t")
}

func TestAdvStringEscapesPreserved(t *testing.T) {
	advAllow(t, "SELECT 'it''s insert into t'")
	advAllow(t, `SELECT "a""update" FROM t`)
	advAllow(t, "SELECT 'multi\nline delete from t'")
}

func TestAdvWhitespaceBeforeSelect(t *testing.T) {
	advAllow(t, "\n\t  SELECT 1")
	advAllow(t, "   with x as (select 1) select * from x")
}

func TestAdvErrorMessagesNonEmpty(t *testing.T) {
	err := AssertReadOnlySQL("DELETE FROM t")
	if err == nil {
		t.Fatalf("期望非 nil error")
	}
	if strings.TrimSpace(err.Error()) == "" {
		t.Errorf("错误信息不应为空")
	}
}
