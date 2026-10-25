// 职责：消息可见性（visibility / visible_to）的收件人计算与组合校验。纯函数，无副作用、无 IO。
// 生成来源：BotsRouter GLM-5.3（大上下文调用），经本轮人工改编：放进 protocol 包，codec 与网关共用同一份校验，不留两份重复逻辑。
// visibility 缺省表示不启用可见性语义，按原房间路由广播。

/** 可见性模式；缺省表示按原房间路由广播。 */
export type Visibility = "direct" | "restricted";

/** visible_to 单项最大字符数。 */
export const VISIBILITY_RECIPIENT_MAX = 64;

/**
 * 计算一条消息的实际收件人集合。
 * - direct：仅发送者与 visibleTo[0]。
 * - restricted：发送者与 visibleTo 全体。
 * - visibility 缺省：返回 null，表示按原房间路由广播。
 * 入参应先经 validateVisibility 校验通过；此处对越界输入仅做保守兜底。
 */
export function visibleRecipients(
  sender: string,
  visibility: Visibility | undefined,
  visibleTo: string[] | undefined,
): Set<string> | null {
  if (visibility === undefined) return null;
  if (visibility === "direct") {
    const target = visibleTo?.[0];
    return target === undefined ? new Set<string>([sender]) : new Set<string>([sender, target]);
  }
  return new Set<string>([sender, ...(visibleTo ?? [])]);
}

/**
 * 校验 visibility / visible_to 组合，返回错误列表（空表示通过）。
 * - visibility 只能是 direct/restricted；缺省时不启用可见性语义（此时携带 visible_to 报错）。
 * - direct 要求 visibleTo 恰好 1 项；restricted 要求至少 1 项。
 * - 每项非空且不超过 64 字符；重复项报错。
 */
export function validateVisibility(visibility: unknown, visibleTo: unknown): string[] {
  const errs: string[] = [];

  if (visibility === undefined) {
    if (visibleTo !== undefined) {
      errs.push("visible_to: only allowed when visibility is 'direct' or 'restricted'");
    }
    return errs;
  }

  if (visibility !== "direct" && visibility !== "restricted") {
    errs.push("visibility: must be 'direct' or 'restricted'");
    return errs;
  }

  if (!Array.isArray(visibleTo) || !visibleTo.every((r) => typeof r === "string")) {
    errs.push("visible_to: must be a string[]");
    return errs;
  }

  const recipients = visibleTo as string[];

  if (visibility === "direct" && recipients.length !== 1) {
    errs.push("visible_to: must contain exactly 1 recipient when visibility is 'direct'");
  }
  if (visibility === "restricted" && recipients.length < 1) {
    errs.push("visible_to: must contain at least 1 recipient when visibility is 'restricted'");
  }

  recipients.forEach((r, i) => {
    if (r.length === 0 || r.length > VISIBILITY_RECIPIENT_MAX) {
      errs.push(
        `visible_to[${i}]: must be a non-empty string of at most ${VISIBILITY_RECIPIENT_MAX} chars`,
      );
    }
  });

  const seen = new Set<string>();
  for (const r of recipients) {
    if (seen.has(r)) {
      errs.push(`visible_to: duplicate recipient '${r}'`);
      break;
    }
    seen.add(r);
  }

  return errs;
}
