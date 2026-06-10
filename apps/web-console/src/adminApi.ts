import type { ThemeMode } from "./adminTypes";

const adminTokenStorageKey = "kaka_admin_token";
const themeStorageKey = "kaka_admin_theme";

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  if (options?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const adminToken = readAdminToken();
  if (adminToken && !headers.has("X-Kaka-Admin-Token")) {
    headers.set("X-Kaka-Admin-Token", adminToken);
  }

  const response = await fetch(`/admin/api${path}`, { ...options, headers });
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return response.json() as Promise<T>;
}

async function parseErrorMessage(response: Response): Promise<string> {
  const fallback = response.statusText || `HTTP ${response.status}`;
  let text = "";

  try {
    text = await response.text();
  } catch {
    return fallback;
  }

  if (!text) return fallback;

  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail) return JSON.stringify(body.detail);
  } catch {
    return text;
  }

  return text;
}

export function readAdminToken(): string {
  try {
    return sessionStorage.getItem(adminTokenStorageKey)?.trim() ?? "";
  } catch {
    return "";
  }
}

export function writeAdminToken(value: string): void {
  try {
    const token = value.trim();
    if (token) {
      sessionStorage.setItem(adminTokenStorageKey, token);
    } else {
      sessionStorage.removeItem(adminTokenStorageKey);
    }
  } catch {
    return;
  }
}

export function readThemeMode(): ThemeMode {
  try {
    return localStorage.getItem(themeStorageKey) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function writeThemeMode(value: ThemeMode): void {
  try {
    localStorage.setItem(themeStorageKey, value);
  } catch {
    return;
  }
}

export function buildQuery(params: Record<string, string | number | null | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    const text = String(value ?? "").trim();
    if (text) {
      query.set(key, text);
    }
  }
  return query.toString();
}
