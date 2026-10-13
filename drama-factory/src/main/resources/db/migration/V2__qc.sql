-- =============================================================================
-- V2__qc.sql —— 成片质检字段
-- -----------------------------------------------------------------------------
-- 为 final_cuts 表新增质检三字段：
--   qc_status  质检状态：PENDING（待质检）/ APPROVED（通过）/ REJECTED（打回）
--   qc_note    质检备注 / 打回原因
--   qc_at      质检时间
-- 历史成片统一回填为 PENDING。
-- =============================================================================

ALTER TABLE "PUBLIC"."FINAL_CUTS" ADD COLUMN "QC_STATUS" CHARACTER VARYING(20);
ALTER TABLE "PUBLIC"."FINAL_CUTS" ADD COLUMN "QC_NOTE" CHARACTER VARYING(2000);
ALTER TABLE "PUBLIC"."FINAL_CUTS" ADD COLUMN "QC_AT" TIMESTAMP(6);

UPDATE "PUBLIC"."FINAL_CUTS" SET "QC_STATUS" = 'PENDING' WHERE "QC_STATUS" IS NULL;
