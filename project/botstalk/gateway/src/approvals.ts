import type { Envelope, MessagePayload } from "@botstalk/protocol";

/** 一个挂起等待人工放行的任务。原始任务帧保留在 env 里，放行后原样派发。 */
export interface PendingApproval {
  approval_id: string;
  task_id: string;
  room: string;
  /** 提出任务的发送方 id。 */
  requester: string;
  /** 将执行任务的 adapter id。 */
  assignee: string;
  title: string;
  env: Envelope<MessagePayload>;
  expires_at_ms: number;
}

/** 待审批任务的内存登记表。网关重启即丢（与 resendQueue 同为内存态，已知边界）。 */
export class PendingApprovals {
  private readonly map = new Map<string, PendingApproval>();

  put(p: PendingApproval): void {
    this.map.set(p.approval_id, p);
  }

  get(approvalId: string): PendingApproval | undefined {
    return this.map.get(approvalId);
  }

  /** 取出并删除。不存在返回 undefined。 */
  take(approvalId: string): PendingApproval | undefined {
    const p = this.map.get(approvalId);
    if (p !== undefined) {
      this.map.delete(approvalId);
    }
    return p;
  }

  /** 返回全部待审批项的数组快照（只读遍历用）。 */
  list(): PendingApproval[] {
    return [...this.map.values()];
  }

  /** 删除全部已过期条目并返回它们。 */
  sweepExpired(now: number): PendingApproval[] {
    const expired: PendingApproval[] = [];
    for (const p of this.map.values()) {
      if (p.expires_at_ms <= now) {
        expired.push(p);
      }
    }
    for (const p of expired) {
      this.map.delete(p.approval_id);
    }
    return expired;
  }

  get size(): number {
    return this.map.size;
  }
}
