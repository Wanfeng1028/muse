/** Agent 描述符 logo */
export interface Logo {
  key: string;
}

/** 支持能力（三字段全可选，cursor/opencode 原始为空对象 {}） */
export interface Support {
  install?: boolean;
  workspace?: boolean;
  collaboration?: boolean;
}

/** 安装信息 */
export interface InstallInfo {
  binary: string;
  requires?: string[];
  macos: string;
  linux: string;
  windows: string;
}

/** 卸载信息 */
export interface UninstallInfo {
  macos: string;
  linux: string;
  windows: string;
}

/** 适配器 */
export interface Adapter {
  module: string;
  class: string;
}

/** 启动配置，args 允许 null 元素（如 codex 的 [null]） */
export interface Launch {
  args: (string | null)[];
}

/** 就绪检查（所有字段全可选） */
export interface CheckReady {
  env_vars?: string[];
  env_all?: string[];
  saved_env_all?: string[];
  creds_file?: string;
  creds_key?: string;
  creds_no_parse?: string;
  keychain_service?: string;
  not_ready_message?: string;
  login_command?: string;
  alt_check?: string;
  status_args?: string[];
  logged_in_pattern?: string;
  logged_out_pattern?: string;
  unverifiable?: string;
}

/** 探测配置 */
export interface Probe {
  args: string[];
  timeout_s: number;
  skip_cli_with_key?: string;
}

/** 环境变量配置项 */
export interface EnvConfigItem {
  name: string;
  description: string;
  required: boolean;
  password?: boolean;
  default_value?: string;
}

/** resolve_env 规则 */
export interface ResolveEnvRule {
  from: string;
  to: string;
  if_base_url_contains?: string;
  unless_base_url_contains?: string;
}

/** resolve_env */
export interface ResolveEnv {
  rules: ResolveEnvRule[];
}

/** Agent 描述符（22 个描述符字段全集） */
export interface AgentDescriptor {
  name: string;
  label: string;
  description: string;
  homepage: string;
  tags: string[];
  featured: boolean;
  order: number;
  builtin: boolean;
  logo: Logo;
  support: Support;
  install: InstallInfo;
  uninstall?: UninstallInfo;
  adapter: Adapter | null;
  launch: Launch | null;
  check_ready: CheckReady;
  probe?: Probe;
  env_config: EnvConfigItem[];
  /** 结构不统一，宽松类型 */
  models?: Record<string, unknown>;
  vendor: string;
  tagline: string;
  /** 宽松类型 */
  catalog?: Record<string, unknown>;
  workspace_model?: boolean;
  protocol?: string;
  resolve_env?: ResolveEnv;
  provider_locked?: boolean;
}
