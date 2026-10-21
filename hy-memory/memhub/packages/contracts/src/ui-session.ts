/**
 * Core Web Console session contract.
 *
 * The CLI never puts the Core bearer token in a browser URL. It obtains a
 * one-time exchange code and opens the returned loopback URL; Core consumes
 * the code and sets an HttpOnly, SameSite=Strict session cookie.
 */

export interface UISessionExchange {
  schema_version: 1;
  exchange_code: string;
  expires_in_seconds: number;
  url: string;
}

export interface UISessionLogout {
  schema_version: 1;
  state: "logged_out";
}

export type UISessionFailureCode =
  | "ui_web_assets_unavailable"
  | "ui_session_code_invalid"
  | "ui_session_contract_unavailable";
