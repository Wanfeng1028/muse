/** Keeps test traffic away from the daily Core: any in-process axios request
 * that targets the daily loopback port fails here instead of reaching a real
 * instance. Subprocess probes are covered separately by each test's env.
 */
const DAILY_PORTS = new Set(["8765", "18765"]);

function loopbackPort(url: string): string | null {
  try {
    const parsed = new URL(url);
    const loopback =
      parsed.hostname === "127.0.0.1" ||
      parsed.hostname === "localhost" ||
      parsed.hostname === "[::1]";
    return loopback ? (parsed.port === "" ? "80" : parsed.port) : null;
  } catch {
    return null;
  }
}

const axios = require("axios");
const originalRequest = axios.default?.request?.bind(axios.default);

if (axios.default && originalRequest) {
  axios.default.request = (config: { url?: string; baseURL?: string }) => {
    const target = config?.url ?? "";
    const base = config?.baseURL ?? "";
    const port = loopbackPort(target) ?? loopbackPort(base);
    if (port !== null && DAILY_PORTS.has(port)) {
      return Promise.reject(
        new Error(
          `daily_port_guard: test attempted to reach ${base}${target} ` +
            `(port ${port}). The daily Core must never see test traffic.`,
        ),
      );
    }
    return originalRequest(config);
  };
}
