import {
  Archive,
  Brain,
  CheckCircle2,
  Clock3,
  HardDrive,
  LayoutDashboard,
  Moon,
  RefreshCw,
  Search,
  ShieldCheck,
  Sun,
  Trash2,
  Wrench
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

type Summary = {
  counts: Record<string, number>;
  memory_statuses: Record<string, number>;
  settings: Record<string, string | number | boolean | null | undefined>;
  server_time: string;
};

type UserInfo = {
  platform_user_id: string;
  display_name: string;
};

type SceneInfo = {
  scene_type: string;
  scene_type_label: string;
  scene_id: string;
};

type Memory = {
  id: number;
  source_candidate_id?: number | null;
  candidate_id?: number | null;
  memory_text: string;
  normalized_text: string;
  memory_type: string;
  confidence: number;
  source_text: string;
  source: string;
  status: string;
  merge_reason: string;
  created_at: string;
  updated_at: string;
  user?: UserInfo | null;
  scene?: SceneInfo | null;
};

type SearchResult = {
  memory: Memory;
  scene?: SceneInfo | null;
  score: number;
  matched_terms: string[];
  reasons: string[];
};

type SearchForm = {
  user_id: string;
  group_id: string;
  text: string;
  private: boolean;
  min_score: number;
};

type MemoryFilters = {
  ids: string;
  user_id: string;
  group_id: string;
  date: string;
  memory_type: string;
};

type MemoryStatusFilter = "active" | "archived" | "all";
type PageKey = "overview" | "memories" | "search" | "status" | "reserved";
type ThemeMode = "light" | "dark";

type NavItem = {
  id: PageKey;
  label: string;
  icon: LucideIcon;
};

const adminTokenStorageKey = "kaka_admin_token";
const themeStorageKey = "kaka_admin_theme";

const memoryStatusOptions: { value: MemoryStatusFilter; label: string }[] = [
  { value: "active", label: "使用中" },
  { value: "archived", label: "已归档" },
  { value: "all", label: "全部" }
];

const memoryTypeOptions = [
  { value: "", label: "全部类型" },
  { value: "user_fact", label: "用户事实" },
  { value: "stable_preference", label: "稳定偏好" },
  { value: "relationship_fact", label: "关系事实" },
  { value: "important_event", label: "重要事件" },
  { value: "fact", label: "事实" },
  { value: "preference", label: "偏好" }
];

const mainNavItems: NavItem[] = [
  { id: "overview", label: "总览", icon: LayoutDashboard },
  { id: "memories", label: "正式记忆", icon: Brain },
  { id: "search", label: "回复检索", icon: Search },
  { id: "status", label: "运行状态", icon: ShieldCheck }
];

const reservedNavItem: NavItem = { id: "reserved", label: "预留扩展", icon: Wrench };

const pageCopy: Record<PageKey, { title: string; desc: string }> = {
  overview: {
    title: "总览",
    desc: "查看卡咔当前记忆规模、回复注入和运行概况。"
  },
  memories: {
    title: "正式记忆",
    desc: "查看、筛选、归档、恢复和硬删除已经写入长期库的记忆。"
  },
  search: {
    title: "回复检索",
    desc: "模拟回复前的记忆检索，检查当前消息会命中哪些正式记忆。"
  },
  status: {
    title: "运行状态",
    desc: "查看影响记忆调用和后台处理的关键配置。"
  },
  reserved: {
    title: "预留扩展",
    desc: "这里保留给后续新增的管理模块。"
  }
};

const emptyMemoryFilters: MemoryFilters = {
  ids: "",
  user_id: "",
  group_id: "",
  date: "",
  memory_type: ""
};

async function api<T>(path: string, options?: RequestInit): Promise<T> {
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
    let message = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (body.detail) {
        message = JSON.stringify(body.detail);
      }
    } catch {
      const text = await response.text();
      if (text) {
        message = text;
      }
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

function readAdminToken(): string {
  try {
    return sessionStorage.getItem(adminTokenStorageKey)?.trim() ?? "";
  } catch {
    return "";
  }
}

function writeAdminToken(value: string): void {
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

function readThemeMode(): ThemeMode {
  try {
    return localStorage.getItem(themeStorageKey) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function writeThemeMode(value: ThemeMode): void {
  try {
    localStorage.setItem(themeStorageKey, value);
  } catch {
    return;
  }
}

function buildQuery(params: Record<string, string | number | null | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    const text = String(value ?? "").trim();
    if (text) {
      query.set(key, text);
    }
  }
  return query.toString();
}

function formatUser(user?: UserInfo | null): string {
  if (!user) return "-";
  return `${user.display_name || user.platform_user_id}（${user.platform_user_id}）`;
}

function formatScene(scene?: SceneInfo | null): string {
  if (!scene) return "-";
  return `${scene.scene_type_label || scene.scene_type} / ${scene.scene_id}`;
}

function formatConfidence(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "-";
}

function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    active: "使用中",
    archived: "已归档",
    all: "全部"
  };
  return labels[value] ?? value;
}

function statusClass(value: string): string {
  if (value === "active") return "green";
  if (value === "archived") return "gray";
  return "blue";
}

function settingText(value: string | number | boolean | null | undefined, fallback = "-"): string {
  if (typeof value === "boolean") return value ? "开启" : "关闭";
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function memoryTypeLabel(value: string): string {
  const found = memoryTypeOptions.find((item) => item.value === value);
  return found?.label ?? value;
}

function describeSelection(values: number[]): string {
  if (values.length > 8) {
    return `${values.slice(0, 8).join("、")} 等 ${values.length} 条`;
  }
  return values.join("、");
}

export function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [memoryStatus, setMemoryStatus] = useState<MemoryStatusFilter>("active");
  const [memoryFilters, setMemoryFilters] = useState<MemoryFilters>(emptyMemoryFilters);
  const [selectedMemories, setSelectedMemories] = useState<Set<number>>(new Set());
  const [searchForm, setSearchForm] = useState<SearchForm>({
    user_id: "",
    group_id: "",
    text: "",
    private: false,
    min_score: 1
  });
  const [adminToken, setAdminToken] = useState(readAdminToken);
  const [notice, setNotice] = useState("正在加载管理平台");
  const [noticeKind, setNoticeKind] = useState<"info" | "success">("info");
  const [error, setError] = useState("");
  const [busyLabel, setBusyLabel] = useState("");
  const [activePage, setActivePage] = useState<PageKey>("overview");
  const [themeMode, setThemeMode] = useState<ThemeMode>(readThemeMode);

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode;
    writeThemeMode(themeMode);
  }, [themeMode]);

  useEffect(() => {
    void run("刷新页面", refreshAll, { quietSuccess: true });
  }, []);

  const counts = summary?.counts ?? {};
  const settings = summary?.settings ?? {};
  const selectedMemoryIds = useMemo(() => Array.from(selectedMemories), [selectedMemories]);
  const allVisibleSelected = memories.length > 0 && memories.every((memory) => selectedMemories.has(memory.id));
  const isBusy = Boolean(busyLabel);
  const currentPage = pageCopy[activePage];

  async function run(
    label: string,
    task: () => Promise<string | void>,
    options: { quietSuccess?: boolean } = {}
  ) {
    setBusyLabel(label);
    setError("");
    setNoticeKind("info");
    setNotice(`${label}...`);
    try {
      const message = await task();
      setNoticeKind("success");
      setNotice(options.quietSuccess ? "数据已更新" : message || `${label}完成`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setNoticeKind("info");
      setNotice(`${label}失败`);
    } finally {
      setBusyLabel("");
    }
  }

  async function refreshAll() {
    await Promise.all([refreshSummary(), refreshMemories(memoryStatus, memoryFilters)]);
  }

  async function refreshSummary() {
    const data = await api<Summary>("/summary");
    setSummary(data);
  }

  async function refreshMemories(status = memoryStatus, filters = memoryFilters) {
    const query = buildQuery({ limit: 80, status, ...filters });
    const data = await api<{ items: Memory[] }>(`/memories?${query}`);
    setMemories(data.items);
    setSelectedMemories(new Set());
  }

  function updateAdminToken(value: string) {
    setAdminToken(value);
    writeAdminToken(value);
  }

  function changeThemeMode() {
    setThemeMode((value) => (value === "light" ? "dark" : "light"));
  }

  function changeMemoryStatus(value: MemoryStatusFilter) {
    setMemoryStatus(value);
    void run("刷新记忆", () => refreshMemories(value, memoryFilters), { quietSuccess: true });
  }

  function applyFilters() {
    void run("刷新记忆", () => refreshMemories(memoryStatus, memoryFilters), { quietSuccess: true });
  }

  function clearFilters() {
    setMemoryFilters(emptyMemoryFilters);
    void run("刷新记忆", () => refreshMemories(memoryStatus, emptyMemoryFilters), { quietSuccess: true });
  }

  function toggleSelection(id: number) {
    const next = new Set(selectedMemories);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelectedMemories(next);
  }

  function toggleAllVisible() {
    const next = new Set(selectedMemories);
    if (allVisibleSelected) {
      memories.forEach((memory) => next.delete(memory.id));
    } else {
      memories.forEach((memory) => next.add(memory.id));
    }
    setSelectedMemories(next);
  }

  async function updateMemoryStatus(status: "active" | "archived") {
    if (!selectedMemories.size) return;
    const action = status === "active" ? "恢复" : "归档";
    const ids = Array.from(selectedMemories);
    if (!window.confirm(`确认${action}记忆编号 ${describeSelection(ids)}？`)) return;

    await run(`${action}记忆`, async () => {
      const result = await api<{ updated: number; matched: number }>("/memories/status", {
        method: "POST",
        body: JSON.stringify({ ids, status })
      });
      await Promise.all([refreshMemories(memoryStatus, memoryFilters), refreshSummary()]);
      return `匹配 ${result.matched} 条，更新 ${result.updated} 条`;
    });
  }

  async function deleteSelectedMemories() {
    if (!selectedMemories.size) return;
    const ids = Array.from(selectedMemories);
    if (!window.confirm(`确认永久删除记忆编号 ${describeSelection(ids)}？此操作不可撤销。`)) return;

    await run("删除记忆", async () => {
      const result = await api<{ deleted: number }>("/memories/delete", {
        method: "POST",
        body: JSON.stringify({ ids, confirm: true })
      });
      await Promise.all([refreshMemories(memoryStatus, memoryFilters), refreshSummary()]);
      return `删除 ${result.deleted} 条`;
    });
  }

  async function searchMemories() {
    await run("检索记忆", async () => {
      const data = await api<{ items: SearchResult[] }>("/memories/search", {
        method: "POST",
        body: JSON.stringify(searchForm)
      });
      setSearchResults(data.items);
      return `命中 ${data.items.length} 条`;
    });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">卡</div>
          <div>
            <strong>卡咔</strong>
            <span>记忆管理平台</span>
          </div>
        </div>

        <nav className="nav-list" aria-label="主导航">
          <div className="nav-group">
            {mainNavItems.map((item) => (
              <NavButton
                active={activePage === item.id}
                icon={item.icon}
                key={item.id}
                label={item.label}
                onClick={() => setActivePage(item.id)}
              />
            ))}
          </div>
          <div className="nav-reserved">
            <span>后续模块</span>
            <NavButton
              active={activePage === reservedNavItem.id}
              icon={reservedNavItem.icon}
              label={reservedNavItem.label}
              onClick={() => setActivePage(reservedNavItem.id)}
            />
          </div>
        </nav>

        <div className="sidebar-footer">
          <button
            aria-pressed={themeMode === "dark"}
            className="theme-switch"
            onClick={changeThemeMode}
            type="button"
          >
            <span className="switch-track">
              <span className="switch-thumb">{themeMode === "light" ? <Sun size={13} /> : <Moon size={13} />}</span>
            </span>
            <span>双色模式：{themeMode === "light" ? "浅色" : "深色"}</span>
          </button>
          <div className="sidebar-card">
            <span>服务器时间</span>
            <strong>{summary?.server_time ?? "未连接"}</strong>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">卡咔管理平台</p>
            <h1>{currentPage.title}</h1>
            <p className="lead">{currentPage.desc}</p>
          </div>
          <div className="status-strip" aria-label="管理状态">
            <span className="time-chip">
              <Clock3 size={15} />
              {summary?.server_time ?? "未连接"}
            </span>
            <label className="token-field">
              <span>管理密钥</span>
              <input
                autoComplete="off"
                placeholder="需要时填写"
                type="password"
                value={adminToken}
                onChange={(event) => updateAdminToken(event.target.value)}
              />
            </label>
            <button
              className="icon-button"
              disabled={isBusy}
              onClick={() => void run("刷新页面", refreshAll, { quietSuccess: true })}
              title="刷新页面"
              type="button"
            >
              <RefreshCw size={18} />
            </button>
          </div>
        </header>

        {error ? <div className="alert error">{error}</div> : <div className={`alert ${noticeKind}`}>{notice}</div>}

        <div className="page-frame" key={activePage}>
          {activePage === "overview" && (
            <OverviewPage
              counts={counts}
              settings={settings}
              serverTime={summary?.server_time ?? "未连接"}
              onOpenMemories={() => setActivePage("memories")}
              onOpenSearch={() => setActivePage("search")}
            />
          )}
          {activePage === "memories" && (
            <MemoriesPage
              allVisibleSelected={allVisibleSelected}
              filters={memoryFilters}
              isBusy={isBusy}
              memories={memories}
              memoryStatus={memoryStatus}
              selectedMemories={selectedMemories}
              selectedMemoryIds={selectedMemoryIds}
              onApplyFilters={applyFilters}
              onChangeFilters={setMemoryFilters}
              onChangeStatus={changeMemoryStatus}
              onClearFilters={clearFilters}
              onDelete={() => void deleteSelectedMemories()}
              onRefresh={() =>
                void run("刷新记忆", () => refreshMemories(memoryStatus, memoryFilters), { quietSuccess: true })
              }
              onToggleAll={toggleAllVisible}
              onToggleSelection={toggleSelection}
              onUpdateStatus={(status) => void updateMemoryStatus(status)}
            />
          )}
          {activePage === "search" && (
            <SearchPage
              disabled={isBusy}
              form={searchForm}
              results={searchResults}
              onChange={setSearchForm}
              onSubmit={() => void searchMemories()}
            />
          )}
          {activePage === "status" && <StatusPage counts={counts} settings={settings} serverTime={summary?.server_time ?? "未连接"} />}
          {activePage === "reserved" && <ReservedPage />}
        </div>
      </main>
    </div>
  );
}

function NavButton({
  active,
  icon: Icon,
  label,
  onClick
}: {
  active: boolean;
  icon: LucideIcon;
  label: string;
  onClick: () => void;
}) {
  return (
    <button className={`nav-item ${active ? "active" : ""}`} onClick={onClick} type="button">
      <Icon size={18} />
      <span>{label}</span>
    </button>
  );
}

function OverviewPage({
  counts,
  settings,
  serverTime,
  onOpenMemories,
  onOpenSearch
}: {
  counts: Record<string, number>;
  settings: Summary["settings"];
  serverTime: string;
  onOpenMemories: () => void;
  onOpenSearch: () => void;
}) {
  return (
    <div className="page-stack">
      <section className="stats-grid" aria-label="正式记忆概览">
        <Metric icon={Brain} title="使用中" value={counts.active_memories ?? 0} />
        <Metric icon={Archive} title="已归档" value={counts.archived_memories ?? 0} />
        <Metric icon={HardDrive} title="总记忆" value={counts.memories ?? 0} />
        <Metric icon={ShieldCheck} title="回复注入" value={settingText(settings.memory_reply_injection_enabled)} />
      </section>

      <section className="split-grid">
        <Panel title="快捷操作" subtitle="进入常用管理页">
          <div className="quick-actions">
            <button onClick={onOpenMemories} type="button">
              <Brain size={16} />
              管理正式记忆
            </button>
            <button className="secondary" onClick={onOpenSearch} type="button">
              <Search size={16} />
              测试回复检索
            </button>
          </div>
        </Panel>
        <Panel title="运行摘要" subtitle="当前系统读取到的状态">
          <KeyValueGrid
            data={{
              服务器时间: serverTime,
              回复注入: settingText(settings.memory_reply_injection_enabled),
              注入条数: settingText(settings.memory_reply_limit, "0"),
              最低分: settingText(settings.memory_reply_min_score, "0")
            }}
          />
        </Panel>
      </section>
    </div>
  );
}

function MemoriesPage({
  allVisibleSelected,
  filters,
  isBusy,
  memories,
  memoryStatus,
  selectedMemories,
  selectedMemoryIds,
  onApplyFilters,
  onChangeFilters,
  onChangeStatus,
  onClearFilters,
  onDelete,
  onRefresh,
  onToggleAll,
  onToggleSelection,
  onUpdateStatus
}: {
  allVisibleSelected: boolean;
  filters: MemoryFilters;
  isBusy: boolean;
  memories: Memory[];
  memoryStatus: MemoryStatusFilter;
  selectedMemories: Set<number>;
  selectedMemoryIds: number[];
  onApplyFilters: () => void;
  onChangeFilters: (filters: MemoryFilters) => void;
  onChangeStatus: (value: MemoryStatusFilter) => void;
  onClearFilters: () => void;
  onDelete: () => void;
  onRefresh: () => void;
  onToggleAll: () => void;
  onToggleSelection: (id: number) => void;
  onUpdateStatus: (status: "active" | "archived") => void;
}) {
  return (
    <section className="panel memory-panel">
      <div className="panel-header">
        <div>
          <h2>正式记忆</h2>
          <span>当前显示 {memories.length} 条，已选 {selectedMemories.size} 条</span>
        </div>
      </div>

      <div className="control-bar">
        <label className="compact-field">
          <span>状态</span>
          <select value={memoryStatus} onChange={(event) => onChangeStatus(event.target.value as MemoryStatusFilter)}>
            {memoryStatusOptions.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <SelectionText ids={selectedMemoryIds} />
        <div className="toolbar-actions">
          <button className="secondary" disabled={isBusy} onClick={onRefresh} type="button">
            <RefreshCw size={16} />
            刷新
          </button>
          <button className="secondary" disabled={isBusy || !selectedMemories.size} onClick={() => onUpdateStatus("archived")} type="button">
            <Archive size={16} />
            归档
          </button>
          <button className="secondary" disabled={isBusy || !selectedMemories.size} onClick={() => onUpdateStatus("active")} type="button">
            <CheckCircle2 size={16} />
            恢复
          </button>
          <button className="danger" disabled={isBusy || !selectedMemories.size} onClick={onDelete} type="button">
            <Trash2 size={16} />
            硬删除
          </button>
        </div>
      </div>

      <FilterBar filters={filters} onChange={onChangeFilters} onClear={onClearFilters} onSubmit={onApplyFilters} />

      <DataTable empty="当前筛选下没有正式记忆" isEmpty={!memories.length}>
        <thead>
          <tr>
            <th className="check-col">
              <input checked={allVisibleSelected} disabled={!memories.length} type="checkbox" onChange={onToggleAll} />
            </th>
            <th className="id-col">编号</th>
            <th className="status-col">状态</th>
            <th className="actor-col">用户 / 场景</th>
            <th className="type-col">类型</th>
            <th>记忆内容</th>
            <th className="time-col">更新时间</th>
          </tr>
        </thead>
        <tbody>
          {memories.map((memory) => (
            <tr key={memory.id}>
              <td className="check-col">
                <input
                  checked={selectedMemories.has(memory.id)}
                  type="checkbox"
                  onChange={() => onToggleSelection(memory.id)}
                />
              </td>
              <td className="id-col">#{memory.id}</td>
              <td className="status-col">
                <Badge value={memory.status} />
              </td>
              <td className="actor-col">
                <strong>{formatUser(memory.user)}</strong>
                <small>{formatScene(memory.scene)}</small>
              </td>
              <td className="type-col">{memoryTypeLabel(memory.memory_type || "-")}</td>
              <td className="memory-text">
                <p>{memory.memory_text}</p>
                <small>置信度 {formatConfidence(memory.confidence)}</small>
              </td>
              <td className="time-col">{memory.updated_at || memory.created_at || "-"}</td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </section>
  );
}

function SearchPage({
  form,
  results,
  disabled,
  onChange,
  onSubmit
}: {
  form: SearchForm;
  results: SearchResult[];
  disabled: boolean;
  onChange: (value: SearchForm) => void;
  onSubmit: () => void;
}) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>回复检索</h2>
          <span>输入用户号和当前消息，预览会参与回复的记忆。</span>
        </div>
      </div>
      <div className="search-preview">
        <div className="form-grid">
          <label>
            <span>用户号</span>
            <input value={form.user_id} onChange={(event) => onChange({ ...form, user_id: event.target.value })} />
          </label>
          <label>
            <span>群号</span>
            <input value={form.group_id} onChange={(event) => onChange({ ...form, group_id: event.target.value })} />
          </label>
          <label>
            <span>最低分</span>
            <input
              min="0"
              step="0.1"
              type="number"
              value={form.min_score}
              onChange={(event) => onChange({ ...form, min_score: Number(event.target.value) })}
            />
          </label>
          <label className="checkbox-label">
            <input
              checked={form.private}
              type="checkbox"
              onChange={(event) => onChange({ ...form, private: event.target.checked })}
            />
            <span>私聊场景</span>
          </label>
          <label className="full">
            <span>当前消息</span>
            <textarea value={form.text} onChange={(event) => onChange({ ...form, text: event.target.value })} />
          </label>
        </div>
        <div className="preview-actions">
          <button disabled={disabled || !form.user_id || !form.text} onClick={onSubmit} type="button">
            <Search size={16} />
            开始检索
          </button>
        </div>
        <div className="result-list">
          {results.map((item) => (
            <article className="result-item" key={item.memory.id}>
              <div className="result-head">
                <strong>
                  #{item.memory.id} / {memoryTypeLabel(item.memory.memory_type || "-")}
                </strong>
                <span className="score-badge">分数 {item.score.toFixed(1)}</span>
              </div>
              <p>{item.memory.memory_text}</p>
              <small>{item.reasons.join(" / ") || item.matched_terms.join(" / ") || "暂无命中说明"}</small>
            </article>
          ))}
          {!results.length && <EmptyState message="暂无检索结果" />}
        </div>
      </div>
    </section>
  );
}

function StatusPage({
  counts,
  settings,
  serverTime
}: {
  counts: Record<string, number>;
  settings: Summary["settings"];
  serverTime: string;
}) {
  return (
    <div className="page-stack">
      <section className="stats-grid">
        <Metric icon={Brain} title="正式记忆" value={counts.memories ?? 0} />
        <Metric icon={Archive} title="已归档" value={counts.archived_memories ?? 0} />
        <Metric icon={ShieldCheck} title="自动分析" value={settingText(settings.memory_auto_analysis_enabled)} />
        <Metric icon={CheckCircle2} title="自动审核" value={settingText(settings.memory_auto_review_enabled)} />
      </section>
      <Panel title="配置详情" subtitle="当前管理端读取到的关键配置">
        <KeyValueGrid
          data={{
            服务器时间: serverTime,
            回复注入: settingText(settings.memory_reply_injection_enabled),
            注入条数: settingText(settings.memory_reply_limit, "0"),
            最低分: settingText(settings.memory_reply_min_score, "0"),
            自动分析: settingText(settings.memory_auto_analysis_enabled),
            自动审核: settingText(settings.memory_auto_review_enabled),
            本地管理: settingText(settings.admin_local_only),
            远程模型: settingText(settings.llm_enabled)
          }}
        />
      </Panel>
    </div>
  );
}

function ReservedPage() {
  return (
    <section className="reserved-page">
      <div className="reserved-symbol">
        <Wrench size={26} />
      </div>
      <h2>预留扩展</h2>
      <p>后续需要增加新的管理能力时，可以从这里接入，不影响当前正式记忆管理流程。</p>
    </section>
  );
}

function FilterBar({
  filters,
  onChange,
  onSubmit,
  onClear
}: {
  filters: MemoryFilters;
  onChange: (filters: MemoryFilters) => void;
  onSubmit: () => void;
  onClear: () => void;
}) {
  return (
    <div className="filter-grid">
      <label>
        <span>编号</span>
        <input placeholder="例如：1,2,3" value={filters.ids} onChange={(event) => onChange({ ...filters, ids: event.target.value })} />
      </label>
      <label>
        <span>用户号</span>
        <input value={filters.user_id} onChange={(event) => onChange({ ...filters, user_id: event.target.value })} />
      </label>
      <label>
        <span>群号</span>
        <input value={filters.group_id} onChange={(event) => onChange({ ...filters, group_id: event.target.value })} />
      </label>
      <label>
        <span>日期</span>
        <input type="date" value={filters.date} onChange={(event) => onChange({ ...filters, date: event.target.value })} />
      </label>
      <label>
        <span>类型</span>
        <select value={filters.memory_type} onChange={(event) => onChange({ ...filters, memory_type: event.target.value })}>
          {memoryTypeOptions.map((item) => (
            <option key={item.value || "all"} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <div className="filter-actions">
        <button onClick={onSubmit} type="button">
          应用筛选
        </button>
        <button className="secondary" onClick={onClear} type="button">
          清空
        </button>
      </div>
    </div>
  );
}

function Metric({ title, value, icon: Icon }: { title: string; value: string | number; icon: LucideIcon }) {
  return (
    <div className="metric">
      <Icon size={20} />
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>{title}</h2>
          <span>{subtitle}</span>
        </div>
      </div>
      {children}
    </section>
  );
}

function DataTable({ children, empty, isEmpty }: { children: ReactNode; empty: string; isEmpty: boolean }) {
  return (
    <div className="table-wrap">
      <table>{children}</table>
      {isEmpty && <EmptyState message={empty} />}
    </div>
  );
}

function KeyValueGrid({ data }: { data: Record<string, string | number> }) {
  return (
    <div className="settings-grid">
      {Object.entries(data).map(([key, value]) => (
        <div className="setting-row" key={key}>
          <span>{key}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function SelectionText({ ids }: { ids: number[] }) {
  return <span className="selection-text">{ids.length ? `已选 ${describeSelection(ids)}` : "未选择记忆"}</span>;
}

function EmptyState({ message }: { message: string }) {
  return <div className="empty-state">{message}</div>;
}

function Badge({ value }: { value: string }) {
  return <span className={`badge ${statusClass(value)}`}>{statusLabel(value)}</span>;
}
