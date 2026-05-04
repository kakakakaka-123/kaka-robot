import {
  Archive,
  Brain,
  CheckCircle2,
  GitMerge,
  LayoutDashboard,
  MessageSquareText,
  RotateCcw,
  Search,
  ServerCog,
  ShieldCheck,
  Sparkles,
  Trash2
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type Summary = {
  counts: Record<string, number>;
  candidate_statuses: Record<string, number>;
  memory_statuses: Record<string, number>;
  input_statuses: Record<string, number>;
  settings: Record<string, string | number | boolean>;
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

type Conversation = {
  id: number;
  content_text: string;
  analysis_status: string;
  created_at: string;
  reply_state: string;
  user: UserInfo;
  scene: SceneInfo;
  output?: { content_text: string; output_origin: string; output_reason: string } | null;
};

type InputPreview = Conversation & {
  analysis_label?: string;
  analysis_reason?: string;
  can_mark_skipped?: boolean;
};

type Candidate = {
  id: number;
  source_input_id: number;
  candidate_memory: string;
  source_text: string;
  memory_type: string;
  confidence: number;
  reason: string;
  status: string;
  created_at: string;
  user: UserInfo;
  scene: SceneInfo;
};

type Memory = {
  id: number;
  candidate_id?: number | null;
  source_candidate_id?: number | null;
  memory_text: string;
  memory_type: string;
  confidence: number;
  status: string;
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

type ListFilters = {
  ids: string;
  group_id: string;
  user_id: string;
  date: string;
  scene_type: string;
  memory_type: string;
  reply_state: string;
  output_origin: string;
  output_reason: string;
};

const tabs = [
  { id: "overview", label: "总览", icon: LayoutDashboard },
  { id: "conversations", label: "最近对话", icon: MessageSquareText },
  { id: "inputs", label: "输入分析", icon: Sparkles },
  { id: "candidates", label: "候选区", icon: GitMerge },
  { id: "memories", label: "正式记忆", icon: Brain },
  { id: "search", label: "检索预览", icon: Search },
  { id: "system", label: "系统状态", icon: ServerCog }
] as const;

type TabId = (typeof tabs)[number]["id"];

type NoticeKind = "info" | "success";

const candidateStatusOptions = ["pending", "approved", "rejected", "merged_duplicate", "all"];
const inputStatusOptions = ["not_analyzed", "analyzed", "skipped", "all"];
const memoryStatusOptions = ["active", "archived", "all"];
const sceneTypeOptions = [
  { value: "", label: "全部场景" },
  { value: "group", label: "群聊" },
  { value: "private", label: "私聊" }
];
const replyStateOptions = [
  { value: "", label: "全部回复" },
  { value: "replied", label: "已回复" },
  { value: "no_reply", label: "不回复" },
  { value: "observed", label: "仅观察" }
];
const emptyListFilters: ListFilters = {
  ids: "",
  group_id: "",
  user_id: "",
  date: "",
  scene_type: "",
  memory_type: "",
  reply_state: "",
  output_origin: "",
  output_reason: ""
};
const adminTokenStorageKey = "kaka_admin_token";

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const adminToken = readAdminToken();
  if (adminToken && !headers.has("X-Kaka-Admin-Token")) {
    headers.set("X-Kaka-Admin-Token", adminToken);
  }
  const response = await fetch(`/admin/api${path}`, {
    ...options,
    headers
  });
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
    return localStorage.getItem(adminTokenStorageKey)?.trim() ?? "";
  } catch {
    return "";
  }
}

function writeAdminToken(value: string): void {
  try {
    const token = value.trim();
    if (token) {
      localStorage.setItem(adminTokenStorageKey, token);
    } else {
      localStorage.removeItem(adminTokenStorageKey);
    }
  } catch {
    // localStorage may be unavailable in restricted browsers; the next request will simply omit the token.
  }
}

function joinIds(values: Set<number>): string {
  return Array.from(values).join(", ");
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

function describeSelection(values: number[]): string {
  return values.length > 8 ? `${values.slice(0, 8).join(", ")} 等 ${values.length} 条` : values.join(", ");
}

function confirmWrite(message: string): boolean {
  return window.confirm(message);
}

export function App() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [inputs, setInputs] = useState<InputPreview[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [inputStatus, setInputStatusFilter] = useState("not_analyzed");
  const [candidateStatus, setCandidateStatus] = useState("pending");
  const [memoryStatus, setMemoryStatusFilter] = useState("active");
  const [adminToken, setAdminToken] = useState(readAdminToken);
  const [conversationFilters, setConversationFilters] = useState<ListFilters>(emptyListFilters);
  const [inputFilters, setInputFilters] = useState<ListFilters>(emptyListFilters);
  const [candidateFilters, setCandidateFilters] = useState<ListFilters>(emptyListFilters);
  const [memoryFilters, setMemoryFilters] = useState<ListFilters>(emptyListFilters);
  const [selectedInputs, setSelectedInputs] = useState<Set<number>>(new Set());
  const [selectedCandidates, setSelectedCandidates] = useState<Set<number>>(new Set());
  const [selectedMemories, setSelectedMemories] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState("管理台已加载");
  const [noticeKind, setNoticeKind] = useState<NoticeKind>("info");
  const [error, setError] = useState("");
  const [searchForm, setSearchForm] = useState<SearchForm>({
    user_id: "",
    group_id: "",
    text: "",
    private: false,
    min_score: 1
  });

  async function run(label: string, task: () => Promise<string | void>) {
    setError("");
    setNoticeKind("info");
    setNotice(`${label}...`);
    try {
      const message = await task();
      setNoticeKind("success");
      setNotice(message || `${label}完成`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setNoticeKind("info");
      setNotice(`${label}失败`);
    }
  }

  async function refreshSummary() {
    const data = await api<Summary>("/summary");
    setSummary(data);
  }

  async function refreshConversations() {
    const query = buildQuery({ limit: 50, ...conversationFilters });
    const data = await api<{ items: Conversation[] }>(`/conversations?${query}`);
    setConversations(data.items);
  }

  async function refreshInputs(status = inputStatus, filters = inputFilters) {
    const query = buildQuery({ limit: 50, status, ...filters });
    const data = await api<{ items: InputPreview[] }>(`/inputs/analysis-preview?${query}`);
    setInputs(data.items);
    setSelectedInputs(new Set());
  }

  async function refreshCandidates(status = candidateStatus, filters = candidateFilters) {
    const query = buildQuery({ limit: 50, status, ...filters });
    const data = await api<{ items: Candidate[] }>(`/candidates?${query}`);
    setCandidates(data.items);
    setSelectedCandidates(new Set());
  }

  async function refreshMemories(status = memoryStatus, filters = memoryFilters) {
    const query = buildQuery({ limit: 50, status, ...filters });
    const data = await api<{ items: Memory[] }>(`/memories?${query}`);
    setMemories(data.items);
    setSelectedMemories(new Set());
  }

  async function refreshAll() {
    await Promise.all([
      refreshSummary(),
      refreshConversations(),
      refreshInputs(),
      refreshCandidates(),
      refreshMemories()
    ]);
  }

  useEffect(() => {
    void run("刷新数据", refreshAll);
  }, []);

  const selectedCandidateIds = useMemo(() => Array.from(selectedCandidates), [selectedCandidates]);
  const selectedInputIds = useMemo(() => Array.from(selectedInputs), [selectedInputs]);
  const selectedMemoryIds = useMemo(() => Array.from(selectedMemories), [selectedMemories]);

  function toggleSelection(setter: (value: Set<number>) => void, values: Set<number>, id: number) {
    const next = new Set(values);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setter(next);
  }

  function updateAdminToken(value: string) {
    setAdminToken(value);
    writeAdminToken(value);
  }

  async function markSelectedInputsSkipped() {
    if (!selectedInputIds.length) return;
    if (!confirmWrite(`确认将输入 ID ${describeSelection(selectedInputIds)} 标记为 skipped？`)) return;
    await run("标记 skipped", async () => {
      const result = await api<{ updated: number; skipped: number }>("/inputs/mark-skipped", {
        method: "POST",
        body: JSON.stringify({ ids: selectedInputIds })
      });
      await refreshInputs(inputStatus);
      await refreshSummary();
      return `标记完成：更新 ${result.updated} 条，跳过 ${result.skipped} 条`;
    });
  }

  async function updateInputStatus(status: "not_analyzed" | "analyzed" | "skipped") {
    if (!selectedInputIds.length) return;
    if (!confirmWrite(`确认将输入 ID ${describeSelection(selectedInputIds)} 改为 ${status}？`)) return;
    await run("调整输入状态", async () => {
      const result = await api<{ updated: number; matched: number; status: string }>("/inputs/status", {
        method: "POST",
        body: JSON.stringify({ ids: selectedInputIds, status })
      });
      await refreshInputs(inputStatus);
      await refreshSummary();
      return `输入状态已改为 ${result.status}：匹配 ${result.matched} 条，更新 ${result.updated} 条`;
    });
  }

  async function previewCandidateMerge() {
    if (!selectedCandidateIds.length) return;
    await run("合并预览", async () => {
      const result = await api<{ plan: Record<string, number>; candidate_count: number }>("/candidates/merge", {
        method: "POST",
        body: JSON.stringify({ ids: selectedCandidateIds, apply: false })
      });
      return `预览 ${result.candidate_count} 条：insert=${result.plan.insert ?? 0}, duplicate=${result.plan.duplicate ?? 0}, skip=${result.plan.skip ?? 0}`;
    });
  }

  async function applyCandidateMerge() {
    if (!selectedCandidateIds.length) return;
    if (!confirmWrite(`确认将候选 ID ${describeSelection(selectedCandidateIds)} 写入正式记忆？`)) return;
    await run("合并候选", async () => {
      const result = await api<{ stats: Record<string, number> }>("/candidates/merge", {
        method: "POST",
        body: JSON.stringify({ ids: selectedCandidateIds, apply: true })
      });
      await refreshCandidates(candidateStatus);
      await refreshMemories(memoryStatus);
      await refreshSummary();
      return `合并完成：新增 ${result.stats.inserted ?? 0} 条，重复 ${result.stats.duplicates ?? 0} 条，跳过 ${result.stats.skipped ?? 0} 条`;
    });
  }

  async function updateCandidateStatus(status: "pending" | "approved" | "rejected" | "merged_duplicate") {
    if (!selectedCandidateIds.length) return;
    if (!confirmWrite(`确认将候选 ID ${describeSelection(selectedCandidateIds)} 改为 ${status}？`)) return;
    await run("调整候选状态", async () => {
      const result = await api<{ updated: number; matched: number; status: string }>("/candidates/status", {
        method: "POST",
        body: JSON.stringify({ ids: selectedCandidateIds, status })
      });
      await refreshCandidates(candidateStatus);
      await refreshSummary();
      return `候选状态已改为 ${result.status}：匹配 ${result.matched} 条，更新 ${result.updated} 条`;
    });
  }

  async function updateMemoryStatus(status: "active" | "archived") {
    if (!selectedMemoryIds.length) return;
    const verb = status === "active" ? "恢复" : "归档";
    if (!confirmWrite(`确认${verb}记忆 ID ${describeSelection(selectedMemoryIds)}？`)) return;
    await run(`${verb}记忆`, async () => {
      const result = await api<{ updated: number; matched: number }>("/memories/status", {
        method: "POST",
        body: JSON.stringify({ ids: selectedMemoryIds, status })
      });
      await refreshMemories(memoryStatus);
      await refreshSummary();
      return `${verb}完成：匹配 ${result.matched} 条，更新 ${result.updated} 条`;
    });
  }

  async function deleteSelectedMemories() {
    if (!selectedMemoryIds.length) return;
    if (!confirmWrite(`确认永久删除记忆 ID ${describeSelection(selectedMemoryIds)}？此操作不可撤销。`)) return;
    await run("删除记忆", async () => {
      const result = await api<{ deleted: number }>("/memories/delete", {
        method: "POST",
        body: JSON.stringify({ ids: selectedMemoryIds, confirm: true })
      });
      await refreshMemories(memoryStatus);
      await refreshSummary();
      return `删除完成：${result.deleted} 条`;
    });
  }

  const activeLabel = tabs.find((tab) => tab.id === activeTab)?.label ?? "管理台";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">K</div>
          <div>
            <strong>卡卡管理台</strong>
            <span>Local Admin Console</span>
          </div>
        </div>
        <nav className="nav-list" aria-label="管理台导航">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                className={activeTab === tab.id ? "nav-item active" : "nav-item"}
                onClick={() => setActiveTab(tab.id)}
                type="button"
              >
                <Icon size={18} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <ShieldCheck size={18} />
          <span>本地管理入口，仅面向开发环境</span>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">KAKA V2 OPERATIONS</p>
            <h1>{activeLabel}</h1>
          </div>
          <div className="status-strip">
            <span>{summary?.server_time ?? "未连接"}</span>
            <label className="token-field">
              <span>管理 Token</span>
              <input
                autoComplete="off"
                type="password"
                value={adminToken}
                onChange={(event) => updateAdminToken(event.target.value)}
              />
            </label>
            <button className="icon-button" onClick={() => void run("刷新数据", refreshAll)} title="刷新" type="button">
              <RotateCcw size={18} />
            </button>
          </div>
        </header>

        {error ? <div className="alert error">{error}</div> : <div className={`alert ${noticeKind}`}>{notice}</div>}

        {activeTab === "overview" && <Overview summary={summary} />}
        {activeTab === "conversations" && (
          <Conversations
            rows={conversations}
            filters={conversationFilters}
            onFiltersChange={setConversationFilters}
            onRefresh={() => void run("刷新对话", refreshConversations)}
            onClearFilters={() => {
              setConversationFilters(emptyListFilters);
              void run("刷新对话", async () => {
                const query = buildQuery({ limit: 50, ...emptyListFilters });
                const data = await api<{ items: Conversation[] }>(`/conversations?${query}`);
                setConversations(data.items);
              });
            }}
          />
        )}
        {activeTab === "inputs" && (
          <Inputs
            rows={inputs}
            selected={selectedInputs}
            status={inputStatus}
            filters={inputFilters}
            onStatusChange={(status) => {
              setInputStatusFilter(status);
              void run("刷新输入", () => refreshInputs(status, inputFilters));
            }}
            onFiltersChange={setInputFilters}
            onToggle={(id) => toggleSelection(setSelectedInputs, selectedInputs, id)}
            onRefresh={() => void run("刷新输入", () => refreshInputs(inputStatus, inputFilters))}
            onClearFilters={() => {
              setInputFilters(emptyListFilters);
              void run("刷新输入", () => refreshInputs(inputStatus, emptyListFilters));
            }}
            onMarkSkipped={() => void markSelectedInputsSkipped()}
            onSetStatus={(status) => void updateInputStatus(status)}
          />
        )}
        {activeTab === "candidates" && (
          <Candidates
            rows={candidates}
            selected={selectedCandidates}
            status={candidateStatus}
            filters={candidateFilters}
            onStatusChange={(status) => {
              setCandidateStatus(status);
              void run("刷新候选", () => refreshCandidates(status, candidateFilters));
            }}
            onFiltersChange={setCandidateFilters}
            onRefresh={() => void run("刷新候选", () => refreshCandidates(candidateStatus, candidateFilters))}
            onClearFilters={() => {
              setCandidateFilters(emptyListFilters);
              void run("刷新候选", () => refreshCandidates(candidateStatus, emptyListFilters));
            }}
            onToggle={(id) => toggleSelection(setSelectedCandidates, selectedCandidates, id)}
            onPreview={() => void previewCandidateMerge()}
            onApply={() => void applyCandidateMerge()}
            onSetStatus={(status) => void updateCandidateStatus(status)}
          />
        )}
        {activeTab === "memories" && (
          <Memories
            rows={memories}
            selected={selectedMemories}
            status={memoryStatus}
            filters={memoryFilters}
            onStatusChange={(status) => {
              setMemoryStatusFilter(status);
              void run("刷新记忆", () => refreshMemories(status, memoryFilters));
            }}
            onFiltersChange={setMemoryFilters}
            onRefresh={() => void run("刷新记忆", () => refreshMemories(memoryStatus, memoryFilters))}
            onClearFilters={() => {
              setMemoryFilters(emptyListFilters);
              void run("刷新记忆", () => refreshMemories(memoryStatus, emptyListFilters));
            }}
            onToggle={(id) => toggleSelection(setSelectedMemories, selectedMemories, id)}
            onArchive={() => void updateMemoryStatus("archived")}
            onRestore={() => void updateMemoryStatus("active")}
            onDelete={() => void deleteSelectedMemories()}
          />
        )}
        {activeTab === "search" && (
          <SearchPanel
            form={searchForm}
            results={searchResults}
            onChange={setSearchForm}
            onSubmit={() =>
              void run("检索记忆", async () => {
                const data = await api<{ items: SearchResult[] }>("/memories/search", {
                  method: "POST",
                  body: JSON.stringify(searchForm)
                });
                setSearchResults(data.items);
                return `检索完成：命中 ${data.items.length} 条`;
              })
            }
          />
        )}
        {activeTab === "system" && <SystemPanel summary={summary} />}
      </main>
    </div>
  );
}

function Overview({ summary }: { summary: Summary | null }) {
  const counts = summary?.counts ?? {};
  return (
    <section className="content-grid">
      <Metric title="未分析输入" value={counts.not_analyzed_inputs ?? 0} icon={Sparkles} />
      <Metric title="Pending 候选" value={counts.pending_candidates ?? 0} icon={GitMerge} />
      <Metric title="Active 记忆" value={counts.active_memories ?? 0} icon={Brain} />
      <Metric title="归档记忆" value={counts.archived_memories ?? 0} icon={Archive} />
      <Panel title="记忆状态" className="wide">
        <StatusBars data={summary?.memory_statuses ?? {}} />
      </Panel>
      <Panel title="候选状态" className="wide">
        <StatusBars data={summary?.candidate_statuses ?? {}} />
      </Panel>
      <Panel title="输入状态" className="wide">
        <StatusBars data={summary?.input_statuses ?? {}} />
      </Panel>
      <Panel title="数据规模" className="wide">
        <KeyValueGrid
          data={{
            users: counts.users ?? 0,
            scenes: counts.scenes ?? 0,
            inputs: counts.inputs ?? 0,
            outputs: counts.outputs ?? 0,
            memory_candidates: counts.memory_candidates ?? 0,
            memories: counts.memories ?? 0
          }}
        />
      </Panel>
    </section>
  );
}

function Metric({ title, value, icon: Icon }: { title: string; value: number; icon: typeof Brain }) {
  return (
    <div className="metric">
      <Icon size={20} />
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Panel({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-header">
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

function StatusBars({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data);
  const total = entries.reduce((sum, [, value]) => sum + value, 0) || 1;
  if (!entries.length) {
    return <EmptyState message="暂无状态数据" />;
  }
  return (
    <div className="status-bars">
      {entries.map(([key, value]) => (
        <div key={key} className="status-row">
          <span>{key}</span>
          <div className="bar">
            <div style={{ width: `${Math.max(4, (value / total) * 100)}%` }} />
          </div>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function KeyValueGrid({ data }: { data: Record<string, number | string | boolean> }) {
  return (
    <div className="settings-grid compact">
      {Object.entries(data).map(([key, value]) => (
        <div key={key} className="setting-row">
          <span>{key}</span>
          <strong>{String(value)}</strong>
        </div>
      ))}
    </div>
  );
}

function Conversations({
  rows,
  filters,
  onFiltersChange,
  onRefresh,
  onClearFilters
}: {
  rows: Conversation[];
  filters: ListFilters;
  onFiltersChange: (filters: ListFilters) => void;
  onRefresh: () => void;
  onClearFilters: () => void;
}) {
  return (
    <Panel title="最近 50 条输入">
      <FilterBar
        filters={filters}
        fields={[
          { key: "ids", label: "ID" },
          { key: "group_id", label: "群号" },
          { key: "user_id", label: "用户" },
          { key: "date", label: "日期", type: "date" },
          { key: "scene_type", label: "场景", options: sceneTypeOptions },
          { key: "reply_state", label: "回复", options: replyStateOptions },
          { key: "output_origin", label: "来源" },
          { key: "output_reason", label: "原因" }
        ]}
        onChange={onFiltersChange}
        onSubmit={onRefresh}
        onClear={onClearFilters}
      />
      <Toolbar>
        <button className="secondary" onClick={onRefresh} type="button">
          刷新
        </button>
      </Toolbar>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>时间</th>
              <th>用户</th>
              <th>场景</th>
              <th>回复</th>
              <th>分析</th>
              <th>内容</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.id}</td>
                <td>{row.created_at}</td>
                <td>{formatUser(row.user)}</td>
                <td>{formatScene(row.scene)}</td>
                <td>
                  <Badge value={row.reply_state} />
                </td>
                <td>
                  <Badge value={row.analysis_status} />
                </td>
                <td className="text-cell">
                  {row.content_text}
                  {row.output?.content_text ? <small>回复：{row.output.content_text}</small> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <EmptyState message="暂无对话数据" />}
      </div>
    </Panel>
  );
}

function Inputs({
  rows,
  selected,
  status,
  filters,
  onStatusChange,
  onFiltersChange,
  onToggle,
  onRefresh,
  onClearFilters,
  onMarkSkipped,
  onSetStatus
}: {
  rows: InputPreview[];
  selected: Set<number>;
  status: string;
  filters: ListFilters;
  onStatusChange: (status: string) => void;
  onFiltersChange: (filters: ListFilters) => void;
  onToggle: (id: number) => void;
  onRefresh: () => void;
  onClearFilters: () => void;
  onMarkSkipped: () => void;
  onSetStatus: (status: "not_analyzed" | "analyzed" | "skipped") => void;
}) {
  return (
    <Panel title="未分析输入规则预览">
      <FilterBar
        filters={filters}
        fields={[
          { key: "ids", label: "ID" },
          { key: "group_id", label: "群号" },
          { key: "user_id", label: "用户" },
          { key: "date", label: "日期", type: "date" },
          { key: "scene_type", label: "场景", options: sceneTypeOptions }
        ]}
        onChange={onFiltersChange}
        onSubmit={onRefresh}
        onClear={onClearFilters}
      />
      <Toolbar>
        <select value={status} onChange={(event) => onStatusChange(event.target.value)} aria-label="输入状态">
          {inputStatusOptions.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <SelectionText values={selected} />
        <button className="secondary" onClick={onRefresh} type="button">
          刷新
        </button>
        <button className="danger" disabled={!selected.size} onClick={onMarkSkipped} type="button">
          按规则标记 skipped
        </button>
        <button className="secondary" disabled={!selected.size} onClick={() => onSetStatus("skipped")} type="button">
          设为 skipped
        </button>
        <button className="secondary" disabled={!selected.size} onClick={() => onSetStatus("analyzed")} type="button">
          设为 analyzed
        </button>
        <button className="secondary" disabled={!selected.size} onClick={() => onSetStatus("not_analyzed")} type="button">
          设为 not_analyzed
        </button>
      </Toolbar>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th></th>
              <th>ID</th>
              <th>用户</th>
              <th>场景</th>
              <th>规则结果</th>
              <th>内容</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <input type="checkbox" checked={selected.has(row.id)} onChange={() => onToggle(row.id)} />
                </td>
                <td>{row.id}</td>
                <td>{formatUser(row.user)}</td>
                <td>{formatScene(row.scene)}</td>
                <td>
                  <Badge value={row.analysis_label ?? row.analysis_status} />
                </td>
                <td className="text-cell">
                  {row.content_text}
                  <small>{row.analysis_reason || "暂无规则说明"}</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <EmptyState message="暂无未分析输入" />}
      </div>
    </Panel>
  );
}

function Candidates(props: {
  rows: Candidate[];
  selected: Set<number>;
  status: string;
  filters: ListFilters;
  onStatusChange: (status: string) => void;
  onFiltersChange: (filters: ListFilters) => void;
  onRefresh: () => void;
  onClearFilters: () => void;
  onToggle: (id: number) => void;
  onPreview: () => void;
  onApply: () => void;
  onSetStatus: (status: "pending" | "approved" | "rejected" | "merged_duplicate") => void;
}) {
  const canMerge = props.status === "pending";
  return (
    <Panel title="记忆候选区">
      <FilterBar
        filters={props.filters}
        fields={[
          { key: "ids", label: "ID" },
          { key: "group_id", label: "群号" },
          { key: "user_id", label: "用户" },
          { key: "date", label: "日期", type: "date" },
          { key: "scene_type", label: "场景", options: sceneTypeOptions },
          { key: "memory_type", label: "类型" }
        ]}
        onChange={props.onFiltersChange}
        onSubmit={props.onRefresh}
        onClear={props.onClearFilters}
      />
      <Toolbar>
        <select value={props.status} onChange={(event) => props.onStatusChange(event.target.value)} aria-label="候选状态">
          {candidateStatusOptions.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
        <SelectionText values={props.selected} />
        {canMerge && (
          <>
            <button className="secondary" disabled={!props.selected.size} onClick={props.onPreview} type="button">
              合并预览
            </button>
            <button disabled={!props.selected.size} onClick={props.onApply} type="button">
              写入 memories
            </button>
          </>
        )}
        <button className="secondary" disabled={!props.selected.size} onClick={() => props.onSetStatus("pending")} type="button">
          设为 pending
        </button>
        <button className="secondary" disabled={!props.selected.size} onClick={() => props.onSetStatus("approved")} type="button">
          设为 approved
        </button>
        <button className="danger" disabled={!props.selected.size} onClick={() => props.onSetStatus("rejected")} type="button">
          设为 rejected
        </button>
        <button className="secondary" disabled={!props.selected.size} onClick={() => props.onSetStatus("merged_duplicate")} type="button">
          设为 duplicate
        </button>
      </Toolbar>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th></th>
              <th>ID</th>
              <th>用户</th>
              <th>场景</th>
              <th>类型</th>
              <th>状态</th>
              <th>候选记忆</th>
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <input type="checkbox" checked={props.selected.has(row.id)} onChange={() => props.onToggle(row.id)} />
                </td>
                <td>{row.id}</td>
                <td>{formatUser(row.user)}</td>
                <td>{formatScene(row.scene)}</td>
                <td>{row.memory_type}</td>
                <td>
                  <Badge value={row.status} />
                </td>
                <td className="text-cell">
                  {row.candidate_memory}
                  <small>
                    {row.reason} / confidence {formatConfidence(row.confidence)}
                  </small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!props.rows.length && <EmptyState message="当前筛选下没有候选记忆" />}
      </div>
    </Panel>
  );
}

function Memories(props: {
  rows: Memory[];
  selected: Set<number>;
  status: string;
  filters: ListFilters;
  onStatusChange: (status: string) => void;
  onFiltersChange: (filters: ListFilters) => void;
  onRefresh: () => void;
  onClearFilters: () => void;
  onToggle: (id: number) => void;
  onArchive: () => void;
  onRestore: () => void;
  onDelete: () => void;
}) {
  return (
    <Panel title="正式长期记忆">
      <FilterBar
        filters={props.filters}
        fields={[
          { key: "ids", label: "ID" },
          { key: "group_id", label: "群号" },
          { key: "user_id", label: "用户" },
          { key: "date", label: "日期", type: "date" },
          { key: "scene_type", label: "场景", options: sceneTypeOptions },
          { key: "memory_type", label: "类型" }
        ]}
        onChange={props.onFiltersChange}
        onSubmit={props.onRefresh}
        onClear={props.onClearFilters}
      />
      <Toolbar>
        <select value={props.status} onChange={(event) => props.onStatusChange(event.target.value)} aria-label="记忆状态">
          {memoryStatusOptions.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
        <SelectionText values={props.selected} />
        <button className="secondary" disabled={!props.selected.size} onClick={props.onArchive} type="button">
          <Archive size={16} />
          归档
        </button>
        <button className="secondary" disabled={!props.selected.size} onClick={props.onRestore} type="button">
          <CheckCircle2 size={16} />
          恢复
        </button>
        <button className="danger" disabled={!props.selected.size} onClick={props.onDelete} type="button">
          <Trash2 size={16} />
          删除
        </button>
      </Toolbar>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th></th>
              <th>ID</th>
              <th>用户</th>
              <th>场景</th>
              <th>类型</th>
              <th>状态</th>
              <th>记忆</th>
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <input type="checkbox" checked={props.selected.has(row.id)} onChange={() => props.onToggle(row.id)} />
                </td>
                <td>{row.id}</td>
                <td>{formatUser(row.user)}</td>
                <td>{formatScene(row.scene)}</td>
                <td>{row.memory_type}</td>
                <td>
                  <Badge value={row.status} />
                </td>
                <td className="text-cell">
                  {row.memory_text}
                  <small>
                    {row.updated_at} / confidence {formatConfidence(row.confidence)}
                  </small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!props.rows.length && <EmptyState message="当前筛选下没有正式记忆" />}
      </div>
    </Panel>
  );
}

function SearchPanel({
  form,
  results,
  onChange,
  onSubmit
}: {
  form: SearchForm;
  results: SearchResult[];
  onChange: (value: SearchForm) => void;
  onSubmit: () => void;
}) {
  return (
    <Panel title="回复前记忆检索预览">
      <div className="form-grid">
        <label>
          QQ 用户号
          <input value={form.user_id} onChange={(event) => onChange({ ...form, user_id: event.target.value })} />
        </label>
        <label>
          群号
          <input value={form.group_id} onChange={(event) => onChange({ ...form, group_id: event.target.value })} />
        </label>
        <label>
          最低分
          <input
            type="number"
            min="0"
            step="0.1"
            value={form.min_score}
            onChange={(event) => onChange({ ...form, min_score: Number(event.target.value) })}
          />
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={form.private}
            onChange={(event) => onChange({ ...form, private: event.target.checked })}
          />
          私聊场景
        </label>
        <label className="full">
          当前消息
          <textarea value={form.text} onChange={(event) => onChange({ ...form, text: event.target.value })} />
        </label>
      </div>
      <Toolbar>
        <button disabled={!form.user_id || !form.text} onClick={onSubmit} type="button">
          开始检索
        </button>
      </Toolbar>
      <div className="result-list">
        {results.map((item) => (
          <article key={item.memory.id} className="result-item">
            <div>
              <strong>
                #{item.memory.id} / {item.memory.memory_type}
              </strong>
              <Badge value={`score ${item.score}`} />
            </div>
            <p>{item.memory.memory_text}</p>
            <small>{item.reasons.join(" / ") || item.matched_terms.join(" / ") || "暂无命中说明"}</small>
          </article>
        ))}
        {!results.length && <EmptyState message="填写用户号和当前消息后可预览检索结果" />}
      </div>
    </Panel>
  );
}

function SystemPanel({ summary }: { summary: Summary | null }) {
  return (
    <Panel title="运行配置">
      <KeyValueGrid data={summary?.settings ?? {}} />
    </Panel>
  );
}

type FilterField = {
  key: keyof ListFilters;
  label: string;
  type?: "date";
  options?: { value: string; label: string }[];
};

function FilterBar({
  filters,
  fields,
  onChange,
  onSubmit,
  onClear
}: {
  filters: ListFilters;
  fields: FilterField[];
  onChange: (filters: ListFilters) => void;
  onSubmit: () => void;
  onClear: () => void;
}) {
  return (
    <div className="filter-grid">
      {fields.map((field) => (
        <label key={field.key}>
          {field.label}
          {field.options ? (
            <select
              value={filters[field.key]}
              onChange={(event) => onChange({ ...filters, [field.key]: event.target.value })}
            >
              {field.options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              type={field.type ?? "text"}
              value={filters[field.key]}
              onChange={(event) => onChange({ ...filters, [field.key]: event.target.value })}
            />
          )}
        </label>
      ))}
      <div className="filter-actions">
        <button onClick={onSubmit} type="button">
          应用
        </button>
        <button className="secondary" onClick={onClear} type="button">
          清空
        </button>
      </div>
    </div>
  );
}

function Toolbar({ children }: { children: React.ReactNode }) {
  return <div className="toolbar">{children}</div>;
}

function SelectionText({ values }: { values: Set<number> }) {
  return <span className="selection-text">已选 {values.size}{values.size ? `：${joinIds(values)}` : ""}</span>;
}

function EmptyState({ message }: { message: string }) {
  return <div className="empty-state">{message}</div>;
}

function Badge({ value }: { value: string }) {
  return <span className={`badge ${badgeClass(value)}`}>{value}</span>;
}

function badgeClass(value: string) {
  if (value.includes("active") || value.includes("approved") || value.includes("replied") || value.includes("candidate")) {
    return "green";
  }
  if (value.includes("pending") || value.includes("not_analyzed") || value.includes("score")) {
    return "blue";
  }
  if (value.includes("reject") || value.includes("delete") || value.includes("skipped") || value.includes("archived")) {
    return "red";
  }
  return "gray";
}

function formatUser(user?: UserInfo | null) {
  if (!user) return "-";
  return `${user.display_name} (${user.platform_user_id})`;
}

function formatScene(scene?: SceneInfo | null) {
  if (!scene) return "-";
  return `${scene.scene_type_label || scene.scene_type} / ${scene.scene_id}`;
}

function formatConfidence(value: number) {
  return Number.isFinite(value) ? value.toFixed(2) : "-";
}
