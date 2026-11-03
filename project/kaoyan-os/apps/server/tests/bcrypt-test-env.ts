// 测试提速：必须在所有业务模块之前 import（ESM 按 import 顺序求值），
// 让 src/auth.ts 模块顶层的 BCRYPT_COST IIFE 读到 4 而不是默认 12。
process.env.BCRYPT_COST = process.env.BCRYPT_COST ?? '4';
