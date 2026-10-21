import { Copy, RefreshCw } from "lucide-react";
import { useState } from "react";
import { copyText } from "./copy-text";

type Material = { mcp: string; shell: string | null; prompt: string };
type Mode = keyof Material;

export function ConnectionFallback() {
  const [material, setMaterial] = useState<Material | null>(null);
  const [mode, setMode] = useState<Mode>("prompt");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [notice, setNotice] = useState("");
  const available = !!window.oneMemory?.getConnectionMaterial;

  async function load() {
    const bridge = window.oneMemory;
    if (!bridge?.getConnectionMaterial || loading) return;
    setLoading(true);
    setError(false);
    try {
      setMaterial(await bridge.getConnectionMaterial());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <details
      className="connection-fallback"
      onToggle={(event) => {
        if (event.currentTarget.open && !material && !loading && !error)
          void load();
      }}
    >
      <summary>连接其他工具</summary>
      {!available ? (
        <p>本机连接材料仅在桌面 App 中可用。</p>
      ) : (
        <>
          <p className="connection-boundary">
            仅本机 MCP / 命令工具。纯网页聊天不支持直接连接本机。
          </p>
          <p>列表内工具请用上方一键安装，此处仅供未列出的工具。</p>
          {loading && <p role="status">正在读取本机连接配置…</p>}
          {error && (
            <p role="alert">
              未能读取连接配置。
              <button
                type="button"
                className="quiet"
                onClick={() => void load()}
              >
                <RefreshCw size={15} aria-hidden="true" />
                重试
              </button>
            </p>
          )}
          {material && (
            <>
              <div
                role="tablist"
                aria-label="连接材料格式"
                className="connection-modes"
              >
                {(
                  [
                    ["prompt", "连接提示词"],
                    ["mcp", "MCP 配置"],
                    ["shell", "命令"],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    role="tab"
                    aria-selected={mode === id}
                    disabled={material[id] === null}
                    onClick={() => {
                      setMode(id);
                      setNotice("");
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <textarea
                aria-label="本机连接材料"
                readOnly
                value={material[mode] ?? ""}
                spellCheck={false}
              />
              <p>
                包含本机路径，不含记忆和密钥。片段会运行本机 MemHub
                连接程序；粘贴前请确认，MemHub 需保持运行。
              </p>
              <button
                type="button"
                className="secondary"
                onClick={async () => {
                  try {
                    await copyText(material[mode] ?? "");
                    setNotice("已复制，尚未建立连接。");
                  } catch {
                    setNotice("复制失败，可在上方选中文本复制。");
                  }
                }}
              >
                <Copy size={15} aria-hidden="true" />
                复制
                {mode === "prompt"
                  ? "提示词"
                  : mode === "mcp"
                    ? "配置"
                    : "命令"}
              </button>
              {notice && <p role="status">{notice}</p>}
            </>
          )}
        </>
      )}
    </details>
  );
}
