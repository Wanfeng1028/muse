import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import type { AgentDescriptor, Support } from "./schema.js";

/** 缺省 support（照抄原版 Python Registry） */
export const DEFAULT_SUPPORT: Support = {
  install: true,
  workspace: false,
  collaboration: false,
};

export class Registry {
  private catalog: AgentDescriptor[] | null = null;

  /** 从 descriptors/*.json 加载描述符，补全 support，排序后返回 */
  loadCatalog(): AgentDescriptor[] {
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = dirname(__filename);
    // 包根目录：src 的上一级
    const pkgRoot = join(__dirname, "..");
    const descDir = join(pkgRoot, "descriptors");

    const entries = readdirSync(descDir);
    const descriptors: AgentDescriptor[] = [];

    for (const entry of entries) {
      if (!entry.endsWith(".json")) continue;
      // 跳过 index.json（非描述符文件）
      if (entry === "index.json") continue;
      try {
        const raw = JSON.parse(readFileSync(join(descDir, entry), "utf-8"));
        // 缺 support 或 support 为空对象时补默认值（仅内存，不改 JSON）
        if (
          !raw.support ||
          (typeof raw.support === "object" && Object.keys(raw.support).length === 0)
        ) {
          raw.support = { ...DEFAULT_SUPPORT };
        }
        descriptors.push(raw as AgentDescriptor);
      } catch {
        // 解析失败则跳过
      }
    }

    // 排序：featured 优先（按 order 升序），其余按 (label || name) 字母序
    descriptors.sort((a, b) => {
      if (a.featured && !b.featured) return -1;
      if (!a.featured && b.featured) return 1;
      if (a.featured && b.featured) {
        return a.order - b.order;
      }
      const aKey = a.label || a.name;
      const bKey = b.label || b.name;
      return aKey.localeCompare(bKey);
    });

    this.catalog = descriptors;
    return descriptors;
  }

  /** 获取目录（内存缓存，首次自动加载） */
  getCatalog(): AgentDescriptor[] {
    if (!this.catalog) {
      this.loadCatalog();
    }
    return this.catalog!;
  }

  /** 按 name 精确查找 */
  getByName(name: string): AgentDescriptor | undefined {
    return this.getCatalog().find((d) => d.name === name);
  }

  /** 按 install.binary 查找 */
  findByBinary(binary: string): AgentDescriptor | undefined {
    return this.getCatalog().find((d) => d.install.binary === binary);
  }

  /** 获取 featured 列表 */
  featured(): AgentDescriptor[] {
    return this.getCatalog().filter((d) => d.featured);
  }

  /** 按标签筛选 */
  byTag(tag: string): AgentDescriptor[] {
    return this.getCatalog().filter((d) => d.tags.includes(tag));
  }

  /** 描述符总数 */
  count(): number {
    return this.getCatalog().length;
  }

  /** 校验描述符，返回错误列表（空=合法，允许未知扩展字段） */
  validateDescriptor(d: unknown): string[] {
    const errors: string[] = [];

    if (d === null || typeof d !== "object") {
      errors.push("描述符必须为对象");
      return errors;
    }

    const obj = d as Record<string, unknown>;

    // 非空字符串校验辅助
    const requireNonEmptyString = (key: string) => {
      if (typeof obj[key] !== "string" || (obj[key] as string).length === 0) {
        errors.push(`${key} 必须为非空字符串`);
      }
    };

    requireNonEmptyString("name");
    requireNonEmptyString("label");
    requireNonEmptyString("description");
    requireNonEmptyString("homepage");
    requireNonEmptyString("vendor");
    requireNonEmptyString("tagline");

    // tags 非空数组
    if (!Array.isArray(obj.tags) || obj.tags.length === 0) {
      errors.push("tags 必须为非空数组");
    }

    // featured 布尔
    if (typeof obj.featured !== "boolean") {
      errors.push("featured 必须为布尔值");
    }

    // order 数字
    if (typeof obj.order !== "number") {
      errors.push("order 必须为数字");
    }

    // builtin 布尔
    if (typeof obj.builtin !== "boolean") {
      errors.push("builtin 必须为布尔值");
    }

    // launch.args 是数组（上游有 launch: null 的描述符，null 即跳过）
    if (
      obj.launch !== null &&
      (typeof obj.launch !== "object" ||
        !Array.isArray((obj.launch as Record<string, unknown>).args))
    ) {
      errors.push("launch.args 必须为数组");
    }

    // adapter.module / adapter.class 非空字符串（上游有 adapter: null 的描述符，null 即跳过）
    if (obj.adapter === null || obj.adapter === undefined) {
      // 无 adapter 声明：允许，调用方自行处理
    } else if (typeof obj.adapter === "object") {
      const adapter = obj.adapter as Record<string, unknown>;
      if (typeof adapter.module !== "string" || (adapter.module as string).length === 0) {
        errors.push("adapter.module 必须为非空字符串");
      }
      if (typeof adapter.class !== "string" || (adapter.class as string).length === 0) {
        errors.push("adapter.class 必须为非空字符串");
      }
    } else {
      errors.push("adapter 必须为对象");
    }

    // 允许未知扩展字段（models / catalog 等不报错）
    return errors;
  }
}
