/** 后端的错误代号 → 一句能照着做的话。
 *
 * 之前这一层不存在，`use-model-profiles` 直接把代号返回给界面，于是粘完 key
 * 点「设为当前模型」时，屏幕上出现的是 `model_profile_probe_required`。
 * 代号是给我们排查用的，不是给读它的人用的。
 *
 * 认不出来的代号原样带出去，不换成一句笼统的「出错了」：那样虽然屏幕上不再
 * 出现下划线，但排查线索也一起没了，而下一个人只能回来重现一次。
 */
const TEXT: Record<string, string> = {
  model_profile_probe_required:
    "这张卡还没测过。点一次「设为当前模型」会先自动测，如果还是不行，说明端点、key 或模型名有一处不对。",
  model_provider_not_supported: "这类模型接口暂时用不了，换一张卡。",
  embedding_model_required: "这张卡缺了向量化模型，补上才能启用。",
  model_profile_not_found: "这张卡已经不在了，可能刚被删掉。刷新一下。",
  model_profile_conflict:
    "这张卡刚被改过。刷新一下再试，免得覆盖掉别处的改动。",
};

export function modelErrorText(code: string): string {
  return TEXT[code] ?? `操作没成功：${code}`;
}

export function memoryWriteErrorText(
  code: string | null | undefined,
): string | null {
  if (code?.startsWith("model_content_")) {
    return "原话已保存在本机；当前内容、模型接收方或授权版本尚未通过核对，未继续整理。";
  }
  if (code === "hy_memory_import_no_readable_output") {
    return "HY 未返回可核对的已有记忆，未创建替代内容；原始记录已保留，可重试处理。";
  }
  if (code === "hy_memory_write_verification_historical_support_only") {
    return "历史引用尚未绑定到原始来源，当前批次未完成，原话已保留。";
  }
  if (code?.startsWith("hy_memory_write_verification_")) {
    return "记忆内容未通过来源与作者核验，当前批次未完成，原话已保留。";
  }
  return null;
}
