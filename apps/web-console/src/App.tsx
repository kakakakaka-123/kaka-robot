import {
  Archive,
  Brain,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Clock3,
  Edit3,
  HardDrive,
  History,
  LayoutDashboard,
  Moon,
  Plus,
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
  recent_auto_job_runs: AutoJobRun[];
  settings: Record<string, string | number | boolean | null | undefined>;
  server_time: string;
};

type AutoJobRun = {
  id: number;
  job_name: string;
  job_label: string;
  status: string;
  status_label: string;
  reason: string;
  checked_count: number;
  processed_runs: number;
  inserted_count: number;
  updated_count: number;
  skipped_count: number;
  error_count: number;
  error_message?: string | null;
  started_at: string;
  finished_at: string;
  duration_seconds: number;
};

type AutoJobName = "auto_analysis" | "auto_review";

type AutoJobTriggerSummary = {
  checked_count: number;
  ran: boolean;
  reason: string;
  processed_runs: number;
  candidates_inserted?: number;
  skipped_marked?: number;
  analyzed_marked?: number;
  approved?: number;
  rejected?: number;
  duplicates?: number;
  errors?: number;
};

type AutoJobTriggerResponse = {
  job_name: AutoJobName;
  job_label: string;
  force: boolean;
  summary: AutoJobTriggerSummary;
  latest_run?: AutoJobRun | null;
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

type ReplyContextMessage = {
  role: string;
  content: string;
};

type ReplyContextLayer = {
  name: string;
  title: string;
  role: string;
  content: string;
};

type ReplyContextPreview = {
  messages: ReplyContextMessage[];
  layers: ReplyContextLayer[];
  metadata: Record<string, unknown>;
  used_memory_ids: number[];
  memory_count: number;
  memory_injection_enabled: boolean;
};

type OutputInfo = {
  id: number;
  output_id: string;
  output_origin: string;
  output_reason: string;
  should_reply: boolean;
  no_reply_reason?: string | null;
  content_text: string;
  metadata?: Record<string, unknown>;
  created_at: string;
};

type Conversation = {
  id: number;
  event_id: string;
  content_type: string;
  content_text: string;
  analysis_status: string;
  created_at: string;
  created_at_iso: string;
  user?: UserInfo | null;
  scene?: SceneInfo | null;
  output?: OutputInfo | null;
  reply_state: string;
};

type ConversationDetail = {
  conversation: Conversation;
  metadata: Record<string, unknown>;
  used_memory_ids: number[];
  used_memories: Memory[];
  short_context_input_ids: number[];
  short_context: Conversation[];
};

type SearchForm = {
  user_id: string;
  group_id: string;
  text: string;
  private: boolean;
  min_score: number;
};

type ConversationFilters = {
  ids: string;
  user_id: string;
  group_id: string;
  date: string;
  reply_state: string;
};

type MemoryFilters = {
  ids: string;
  user_id: string;
  group_id: string;
  date: string;
  memory_type: string;
};

type MemoryForm = {
  user_id: string;
  display_name: string;
  group_id: string;
  private: boolean;
  memory_text: string;
  memory_type: string;
  confidence: number;
  source_text: string;
  status: "active" | "archived";
  merge_reason: string;
};

type MemoryStatusFilter = "active" | "archived" | "all";
type PageKey = "overview" | "memories" | "prompt" | "replay" | "status" | "reserved";
type ThemeMode = "light" | "dark";

type NavItem = {
  id: PageKey;
  label: string;
  icon: LucideIcon;
};

const adminTokenStorageKey = "kaka_admin_token";
const themeStorageKey = "kaka_admin_theme";
const memoryPageSize = 50;
const conversationPageSize = 50;

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
  { id: "overview", label: "系统总览", icon: LayoutDashboard },
  { id: "memories", label: "正式记忆", icon: Brain },
  { id: "prompt", label: "提示预演", icon: Search },
  { id: "replay", label: "对话复盘", icon: History },
  { id: "status", label: "运行状态", icon: ShieldCheck }
];

const reservedNavItem: NavItem = { id: "reserved", label: "预留扩展", icon: Wrench };

const pageCopy: Record<PageKey, { title: string; desc: string }> = {
  overview: {
    title: "系统总览",
    desc: "查看卡咔当前记忆规模、回复注入和运行概况。"
  },
  memories: {
    title: "正式记忆",
    desc: "查看、筛选、归档、恢复和硬删除已经写入长期库的记忆。"
  },
  prompt: {
    title: "提示预演",
    desc: "模拟回复前的上下文组装，检查当前消息会命中哪些记忆和提示层。"
  },
  replay: {
    title: "对话复盘",
    desc: "回查卡咔实际回复过的对话，确认当时使用的记忆、短期上下文和关系判断。"
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

const emptyConversationFilters: ConversationFilters = {
  ids: "",
  user_id: "",
  group_id: "",
  date: "",
  reply_state: "replied"
};

const emptyMemoryForm: MemoryForm = {
  user_id: "",
  display_name: "",
  group_id: "",
  private: false,
  memory_text: "",
  memory_type: "user_fact",
  confidence: 0.8,
  source_text: "",
  status: "active",
  merge_reason: ""
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

function numberSetting(settings: Summary["settings"], key: string, fallback = 0): number {
  const value = settings[key];
  const numberValue = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
}

function formatIntervalSeconds(seconds: number): string {
  if (seconds <= 0) return "整点检查";
  if (seconds < 60) return `每 ${seconds} 秒`;
  if (seconds % 3600 === 0) return `每 ${seconds / 3600} 小时`;
  if (seconds % 60 === 0) return `每 ${seconds / 60} 分钟`;
  return `每 ${seconds} 秒`;
}

function queueStateLabel(current: number, threshold: number): string {
  return current >= threshold ? "已达到门槛" : "等待积累";
}

function autoJobStatusClass(status: string): string {
  if (status === "success") return "success";
  if (status === "failed") return "failed";
  return "skipped";
}

function currentQueueLabelForJob(jobName: string, counts: Record<string, number>): string {
  if (jobName === "auto_analysis") return `当前待分析输入 ${counts.not_analyzed_inputs ?? 0}`;
  if (jobName === "auto_review") return `当前待复核候选 ${counts.pending_candidates ?? 0}`;
  return "当前队列未识别";
}

function formatAutoJobTriggerResult(result: AutoJobTriggerResponse): string {
  const { summary } = result;
  if (!summary.ran) {
    return `${result.job_label}跳过：${summary.reason}，检查 ${summary.checked_count} 条`;
  }
  if (result.job_name === "auto_analysis") {
    return (
      `${result.job_label}完成：${summary.processed_runs} 轮，` +
      `新增 ${summary.candidates_inserted ?? 0} 条，标记 ${summary.skipped_marked ?? 0} 条`
    );
  }
  return (
    `${result.job_label}完成：${summary.processed_runs} 轮，` +
    `通过 ${summary.approved ?? 0} 条，拒绝 ${summary.rejected ?? 0} 条，重复 ${summary.duplicates ?? 0} 条`
  );
}

function replyStateLabel(value: string): string {
  const labels: Record<string, string> = {
    replied: "已回复",
    no_reply: "未回复",
    observed: "只观察"
  };
  return labels[value] ?? value;
}

function replyStateClass(value: string): string {
  if (value === "replied") return "green";
  if (value === "no_reply") return "gray";
  return "blue";
}

function conversationMetadata(conversation: Conversation | null | undefined): Record<string, unknown> {
  return conversation?.output?.metadata ?? {};
}

function metadataText(metadata: Record<string, unknown>, key: string, fallback = "-"): string {
  const value = metadata[key];
  if (Array.isArray(value)) {
    return value.length ? value.join("、") : fallback;
  }
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function metadataNumber(metadata: Record<string, unknown>, key: string): string {
  const value = metadata[key];
  if (typeof value === "number") return String(value);
  if (typeof value === "string" && value.trim()) return value;
  return "0";
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
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationDetail, setConversationDetail] = useState<ConversationDetail | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [replyContextPreview, setReplyContextPreview] = useState<ReplyContextPreview | null>(null);
  const [memoryStatus, setMemoryStatus] = useState<MemoryStatusFilter>("active");
  const [memoryFilters, setMemoryFilters] = useState<MemoryFilters>(emptyMemoryFilters);
  const [conversationFilters, setConversationFilters] = useState<ConversationFilters>(emptyConversationFilters);
  const [memoryPage, setMemoryPage] = useState(1);
  const [memoryTotal, setMemoryTotal] = useState(0);
  const [conversationPage, setConversationPage] = useState(1);
  const [conversationTotal, setConversationTotal] = useState(0);
  const [selectedMemories, setSelectedMemories] = useState<Set<number>>(new Set());
  const [memoryFormMode, setMemoryFormMode] = useState<"create" | "edit" | null>(null);
  const [memoryForm, setMemoryForm] = useState<MemoryForm>(emptyMemoryForm);
  const [editingMemoryId, setEditingMemoryId] = useState<number | null>(null);
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
  const memoryTotalPages = Math.max(1, Math.ceil(memoryTotal / memoryPageSize));
  const conversationTotalPages = Math.max(1, Math.ceil(conversationTotal / conversationPageSize));

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
    await Promise.all([
      refreshSummary(),
      refreshMemories(memoryStatus, memoryFilters, memoryPage),
      refreshConversations(conversationFilters, conversationPage)
    ]);
  }

  async function refreshSummary() {
    const data = await api<Summary>("/summary");
    setSummary(data);
  }

  async function refreshMemories(status = memoryStatus, filters = memoryFilters, page = memoryPage) {
    const safePage = Math.max(1, page);
    const offset = (safePage - 1) * memoryPageSize;
    const query = buildQuery({ limit: memoryPageSize, offset, status, ...filters });
    const data = await api<{ items: Memory[]; total: number; limit: number; offset: number }>(`/memories?${query}`);
    if (data.total > 0 && data.items.length === 0 && safePage > 1) {
      const lastPage = Math.max(1, Math.ceil(data.total / memoryPageSize));
      if (lastPage !== safePage) {
        await refreshMemories(status, filters, lastPage);
        return;
      }
    }
    setMemories(data.items);
    setMemoryTotal(data.total);
    setMemoryPage(data.total === 0 ? 1 : Math.max(1, Math.floor(data.offset / (data.limit || memoryPageSize)) + 1));
    setSelectedMemories(new Set());
  }

  async function refreshConversations(filters = conversationFilters, page = conversationPage) {
    const safePage = Math.max(1, page);
    const offset = (safePage - 1) * conversationPageSize;
    const query = buildQuery({ limit: conversationPageSize, offset, ...filters, reply_state: "replied" });
    const data = await api<{ items: Conversation[]; total: number; limit: number; offset: number }>(`/conversations?${query}`);
    if (data.total > 0 && data.items.length === 0 && safePage > 1) {
      const lastPage = Math.max(1, Math.ceil(data.total / conversationPageSize));
      if (lastPage !== safePage) {
        await refreshConversations(filters, lastPage);
        return;
      }
    }
    setConversations(data.items);
    setConversationTotal(data.total);
    setConversationPage(data.total === 0 ? 1 : Math.max(1, Math.floor(data.offset / (data.limit || conversationPageSize)) + 1));
    setConversationDetail((current) =>
      current && data.items.some((conversation) => conversation.id === current.conversation.id) ? current : null
    );
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
    void run("刷新记忆", () => refreshMemories(value, memoryFilters, 1), { quietSuccess: true });
  }

  function applyFilters() {
    void run("刷新记忆", () => refreshMemories(memoryStatus, memoryFilters, 1), { quietSuccess: true });
  }

  function clearFilters() {
    setMemoryFilters(emptyMemoryFilters);
    void run("刷新记忆", () => refreshMemories(memoryStatus, emptyMemoryFilters, 1), { quietSuccess: true });
  }

  function applyConversationFilters() {
    const filters = { ...conversationFilters, reply_state: "replied" };
    setConversationFilters(filters);
    setConversationDetail(null);
    void run("刷新复盘", () => refreshConversations(filters, 1), { quietSuccess: true });
  }

  function clearConversationFilters() {
    setConversationFilters(emptyConversationFilters);
    setConversationDetail(null);
    void run("刷新复盘", () => refreshConversations(emptyConversationFilters, 1), { quietSuccess: true });
  }

  async function openConversationDetail(inputId: number) {
    await run("加载复盘", async () => {
      const detail = await api<ConversationDetail>(`/conversations/${inputId}`);
      setConversationDetail(detail);
      return `已加载输入 #${inputId} 的真实回复复盘`;
    });
  }

  function changeMemoryPage(page: number) {
    if (page < 1 || page > memoryTotalPages || page === memoryPage) return;
    void run("刷新记忆", () => refreshMemories(memoryStatus, memoryFilters, page), { quietSuccess: true });
  }

  function changeConversationPage(page: number) {
    if (page < 1 || page > conversationTotalPages || page === conversationPage) return;
    setConversationDetail(null);
    void run("刷新复盘", () => refreshConversations(conversationFilters, page), { quietSuccess: true });
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

  function startCreateMemory() {
    setMemoryFormMode("create");
    setEditingMemoryId(null);
    setMemoryForm(emptyMemoryForm);
  }

  function startEditMemory() {
    if (selectedMemoryIds.length !== 1) return;
    const memory = memories.find((item) => item.id === selectedMemoryIds[0]);
    if (!memory) return;
    setMemoryFormMode("edit");
    setEditingMemoryId(memory.id);
    setMemoryForm({
      user_id: memory.user?.platform_user_id ?? "",
      display_name: memory.user?.display_name ?? "",
      group_id: memory.scene?.scene_type === "group" ? memory.scene.scene_id : "",
      private: memory.scene?.scene_type === "private",
      memory_text: memory.memory_text,
      memory_type: memory.memory_type || "user_fact",
      confidence: memory.confidence,
      source_text: memory.source_text || "",
      status: memory.status === "archived" ? "archived" : "active",
      merge_reason: memory.merge_reason || ""
    });
  }

  function cancelMemoryForm() {
    setMemoryFormMode(null);
    setEditingMemoryId(null);
    setMemoryForm(emptyMemoryForm);
  }

  async function submitMemoryForm() {
    if (!memoryFormMode) return;
    const mode = memoryFormMode;
    await run(memoryFormMode === "create" ? "新增记忆" : "保存记忆", async () => {
      if (mode === "create") {
        await api<{ item: Memory }>("/memories", {
          method: "POST",
          body: JSON.stringify(memoryForm)
        });
      } else if (editingMemoryId !== null) {
        await api<{ item: Memory }>(`/memories/${editingMemoryId}`, {
          method: "PATCH",
          body: JSON.stringify({ ...memoryForm, scene_update: true })
        });
      }
      cancelMemoryForm();
      await Promise.all([refreshMemories(memoryStatus, memoryFilters, mode === "create" ? 1 : memoryPage), refreshSummary()]);
      return mode === "create" ? "新增记忆完成" : "保存记忆完成";
    });
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
      await Promise.all([refreshMemories(memoryStatus, memoryFilters, 1), refreshSummary()]);
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
      await Promise.all([refreshMemories(memoryStatus, memoryFilters, memoryPage), refreshSummary()]);
      return `删除 ${result.deleted} 条`;
    });
  }

  async function searchMemories() {
    await run("生成预演", async () => {
      const [searchData, contextData] = await Promise.all([
        api<{ items: SearchResult[] }>("/memories/search", {
          method: "POST",
          body: JSON.stringify(searchForm)
        }),
        api<ReplyContextPreview>("/reply-context/preview", {
          method: "POST",
          body: JSON.stringify(searchForm)
        })
      ]);
      setSearchResults(searchData.items);
      setReplyContextPreview(contextData);
      return `命中 ${searchData.items.length} 条，已生成提示上下文预演`;
    });
  }

  async function triggerAutoJob(jobName: AutoJobName) {
    const label = jobName === "auto_analysis" ? "手动触发分析" : "手动触发复核";
    if (!window.confirm(`${label}？会忽略数量门槛，但仍受批次上限、LLM 开关和任务锁限制。`)) return;

    await run(label, async () => {
      const result = await api<AutoJobTriggerResponse>(`/auto-jobs/${jobName}/trigger`, {
        method: "POST",
        body: JSON.stringify({ force: true })
      });
      await refreshSummary();
      return formatAutoJobTriggerResult(result);
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
              onOpenPrompt={() => setActivePage("prompt")}
              onOpenReplay={() => setActivePage("replay")}
            />
          )}
          {activePage === "memories" && (
            <MemoriesPage
              allVisibleSelected={allVisibleSelected}
              filters={memoryFilters}
              isBusy={isBusy}
              memories={memories}
              memoryStatus={memoryStatus}
              page={memoryPage}
              pageSize={memoryPageSize}
              selectedMemories={selectedMemories}
              selectedMemoryIds={selectedMemoryIds}
              total={memoryTotal}
              totalPages={memoryTotalPages}
              form={memoryForm}
              formMode={memoryFormMode}
              onApplyFilters={applyFilters}
              onChangePage={changeMemoryPage}
              onChangeFilters={setMemoryFilters}
              onChangeStatus={changeMemoryStatus}
              onChangeForm={setMemoryForm}
              onClearFilters={clearFilters}
              onCancelForm={cancelMemoryForm}
              onCreate={startCreateMemory}
              onDelete={() => void deleteSelectedMemories()}
              onEdit={startEditMemory}
              onRefresh={() =>
                void run("刷新记忆", () => refreshMemories(memoryStatus, memoryFilters, memoryPage), { quietSuccess: true })
              }
              onSubmitForm={() => void submitMemoryForm()}
              onToggleAll={toggleAllVisible}
              onToggleSelection={toggleSelection}
              onUpdateStatus={(status) => void updateMemoryStatus(status)}
            />
          )}
          {activePage === "prompt" && (
            <PromptPreviewPage
              disabled={isBusy}
              form={searchForm}
              preview={replyContextPreview}
              results={searchResults}
              onChange={setSearchForm}
              onSubmit={() => void searchMemories()}
            />
          )}
          {activePage === "replay" && (
            <ReplayPage
              conversations={conversations}
              detail={conversationDetail}
              disabled={isBusy}
              filters={conversationFilters}
              page={conversationPage}
              pageSize={conversationPageSize}
              total={conversationTotal}
              totalPages={conversationTotalPages}
              onApplyFilters={applyConversationFilters}
              onChangePage={changeConversationPage}
              onChangeFilters={setConversationFilters}
              onClearFilters={clearConversationFilters}
              onOpenDetail={(inputId) => void openConversationDetail(inputId)}
              onRefresh={() => void run("刷新复盘", () => refreshConversations(conversationFilters, conversationPage), { quietSuccess: true })}
            />
          )}
          {activePage === "status" && (
            <StatusPage
              autoJobRuns={summary?.recent_auto_job_runs ?? []}
              counts={counts}
              disabled={isBusy}
              settings={settings}
              serverTime={summary?.server_time ?? "未连接"}
              onTriggerAutoJob={(jobName) => void triggerAutoJob(jobName)}
            />
          )}
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
  onOpenPrompt,
  onOpenReplay
}: {
  counts: Record<string, number>;
  settings: Summary["settings"];
  serverTime: string;
  onOpenMemories: () => void;
  onOpenPrompt: () => void;
  onOpenReplay: () => void;
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
            <button className="secondary" onClick={onOpenPrompt} type="button">
              <Search size={16} />
              打开提示预演
            </button>
            <button className="secondary" onClick={onOpenReplay} type="button">
              <History size={16} />
              查看对话复盘
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
  page,
  pageSize,
  selectedMemories,
  selectedMemoryIds,
  total,
  totalPages,
  form,
  formMode,
  onApplyFilters,
  onChangePage,
  onChangeFilters,
  onChangeStatus,
  onChangeForm,
  onClearFilters,
  onCancelForm,
  onCreate,
  onDelete,
  onEdit,
  onRefresh,
  onSubmitForm,
  onToggleAll,
  onToggleSelection,
  onUpdateStatus
}: {
  allVisibleSelected: boolean;
  filters: MemoryFilters;
  isBusy: boolean;
  memories: Memory[];
  memoryStatus: MemoryStatusFilter;
  page: number;
  pageSize: number;
  selectedMemories: Set<number>;
  selectedMemoryIds: number[];
  total: number;
  totalPages: number;
  form: MemoryForm;
  formMode: "create" | "edit" | null;
  onApplyFilters: () => void;
  onChangePage: (page: number) => void;
  onChangeFilters: (filters: MemoryFilters) => void;
  onChangeStatus: (value: MemoryStatusFilter) => void;
  onChangeForm: (form: MemoryForm) => void;
  onClearFilters: () => void;
  onCancelForm: () => void;
  onCreate: () => void;
  onDelete: () => void;
  onEdit: () => void;
  onRefresh: () => void;
  onSubmitForm: () => void;
  onToggleAll: () => void;
  onToggleSelection: (id: number) => void;
  onUpdateStatus: (status: "active" | "archived") => void;
}) {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(total, page * pageSize);

  return (
    <section className="panel memory-panel">
      <div className="panel-header">
        <div>
          <h2>正式记忆</h2>
          <span>
            第 {page} / {totalPages} 页，当前 {start}-{end} 条，共 {total} 条，已选 {selectedMemories.size} 条
          </span>
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
          <button className="secondary" disabled={isBusy} onClick={onCreate} type="button">
            <Plus size={16} />
            新增
          </button>
          <button className="secondary" disabled={isBusy || selectedMemoryIds.length !== 1} onClick={onEdit} type="button">
            <Edit3 size={16} />
            编辑
          </button>
          <div className="pagination-controls" aria-label="正式记忆分页">
            <button
              className="icon-button secondary"
              disabled={isBusy || page <= 1}
              onClick={() => onChangePage(page - 1)}
              title="上一页"
              type="button"
            >
              <ChevronLeft size={17} />
            </button>
            <span>
              {page} / {totalPages}
            </span>
            <button
              className="icon-button secondary"
              disabled={isBusy || page >= totalPages}
              onClick={() => onChangePage(page + 1)}
              title="下一页"
              type="button"
            >
              <ChevronRight size={17} />
            </button>
          </div>
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

      {formMode && (
        <MemoryEditForm
          disabled={isBusy}
          form={form}
          mode={formMode}
          onCancel={onCancelForm}
          onChange={onChangeForm}
          onSubmit={onSubmitForm}
        />
      )}

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

function MemoryEditForm({
  disabled,
  form,
  mode,
  onCancel,
  onChange,
  onSubmit
}: {
  disabled: boolean;
  form: MemoryForm;
  mode: "create" | "edit";
  onCancel: () => void;
  onChange: (form: MemoryForm) => void;
  onSubmit: () => void;
}) {
  return (
    <div className="memory-form">
      <div className="memory-form-head">
        <div>
          <h3>{mode === "create" ? "新增正式记忆" : "编辑正式记忆"}</h3>
          <span>手动写入的记忆来源会标记为 manual。</span>
        </div>
        <div className="memory-form-actions">
          <button className="secondary" disabled={disabled} onClick={onCancel} type="button">
            取消
          </button>
          <button disabled={disabled || !form.user_id || !form.memory_text || !form.memory_type} onClick={onSubmit} type="button">
            保存
          </button>
        </div>
      </div>
      <div className="memory-form-grid">
        <label>
          <span>用户号</span>
          <input value={form.user_id} onChange={(event) => onChange({ ...form, user_id: event.target.value })} />
        </label>
        <label>
          <span>显示名</span>
          <input value={form.display_name} onChange={(event) => onChange({ ...form, display_name: event.target.value })} />
        </label>
        <label>
          <span>群号</span>
          <input
            disabled={form.private}
            value={form.group_id}
            onChange={(event) => onChange({ ...form, group_id: event.target.value })}
          />
        </label>
        <label className="checkbox-label memory-private-toggle">
          <input
            checked={form.private}
            type="checkbox"
            onChange={(event) => onChange({ ...form, private: event.target.checked })}
          />
          <span>私聊记忆</span>
        </label>
        <label>
          <span>类型</span>
          <select value={form.memory_type} onChange={(event) => onChange({ ...form, memory_type: event.target.value })}>
            {memoryTypeOptions
              .filter((item) => item.value)
              .map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
          </select>
        </label>
        <label>
          <span>置信度</span>
          <input
            max="1"
            min="0"
            step="0.05"
            type="number"
            value={form.confidence}
            onChange={(event) => onChange({ ...form, confidence: Number(event.target.value) })}
          />
        </label>
        <label>
          <span>状态</span>
          <select value={form.status} onChange={(event) => onChange({ ...form, status: event.target.value as "active" | "archived" })}>
            <option value="active">使用中</option>
            <option value="archived">已归档</option>
          </select>
        </label>
        <label className="full">
          <span>记忆内容</span>
          <textarea value={form.memory_text} onChange={(event) => onChange({ ...form, memory_text: event.target.value })} />
        </label>
        <label className="full">
          <span>来源文本</span>
          <textarea value={form.source_text} onChange={(event) => onChange({ ...form, source_text: event.target.value })} />
        </label>
        <label className="full">
          <span>说明</span>
          <input value={form.merge_reason} onChange={(event) => onChange({ ...form, merge_reason: event.target.value })} />
        </label>
      </div>
    </div>
  );
}

function PromptPreviewPage({
  form,
  preview,
  results,
  disabled,
  onChange,
  onSubmit
}: {
  form: SearchForm;
  preview: ReplyContextPreview | null;
  results: SearchResult[];
  disabled: boolean;
  onChange: (value: SearchForm) => void;
  onSubmit: () => void;
}) {
  const systemMessage = preview?.messages.find((item) => item.role === "system");
  const userMessage = preview?.messages.find((item) => item.role === "user");

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>提示预演</h2>
          <span>输入用户号和当前消息，预览回复前会组装出的记忆、关系和 prompt。</span>
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
            开始预演
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
        <div className="context-preview">
          <div className="context-head">
            <div>
              <h3>提示上下文预览</h3>
              <span>只读预览，不调用模型，不写入数据库。</span>
            </div>
            {preview && (
              <div className="context-meta">
                <span>记忆注入：{preview.memory_injection_enabled ? "开启" : "关闭"}</span>
                <span>命中：{preview.memory_count} 条</span>
                <span>编号：{preview.used_memory_ids.length ? preview.used_memory_ids.join("、") : "-"}</span>
              </div>
            )}
          </div>
          {preview ? (
            <div className="prompt-grid">
              <PromptBlock title="System Prompt" content={systemMessage?.content || ""} />
              <PromptBlock title="User Prompt" content={userMessage?.content || ""} />
              <PromptBlock
                title="Prompt Layers"
                content={(preview.layers || [])
                  .map((layer) => `# ${layer.title} (${layer.name} / ${layer.role})\n${layer.content}`)
                  .join("\n\n")}
              />
              <PromptBlock title="Metadata" content={JSON.stringify(preview.metadata, null, 2)} />
            </div>
          ) : (
            <EmptyState message="开始检索后会显示真实回复前的上下文预览" />
          )}
        </div>
      </div>
    </section>
  );
}

function ReplayPage({
  conversations,
  detail,
  disabled,
  filters,
  page,
  pageSize,
  total,
  totalPages,
  onApplyFilters,
  onChangePage,
  onChangeFilters,
  onClearFilters,
  onOpenDetail,
  onRefresh
}: {
  conversations: Conversation[];
  detail: ConversationDetail | null;
  disabled: boolean;
  filters: ConversationFilters;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onApplyFilters: () => void;
  onChangePage: (page: number) => void;
  onChangeFilters: (filters: ConversationFilters) => void;
  onClearFilters: () => void;
  onOpenDetail: (inputId: number) => void;
  onRefresh: () => void;
}) {
  const selectedId = detail?.conversation.id ?? null;
  const detailMetadata = detail ? detail.metadata : {};
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(total, page * pageSize);

  return (
    <section className="page-stack">
      <Panel title="筛选条件" subtitle="按卡咔已回复记录回查，定位当次回复使用的记忆和上下文。">
        <div className="filter-grid replay-filter-grid">
          <label>
            <span>编号</span>
            <input placeholder="例如：1,2,3" value={filters.ids} onChange={(event) => onChangeFilters({ ...filters, ids: event.target.value })} />
          </label>
          <label>
            <span>用户号</span>
            <input value={filters.user_id} onChange={(event) => onChangeFilters({ ...filters, user_id: event.target.value })} />
          </label>
          <label>
            <span>群号</span>
            <input value={filters.group_id} onChange={(event) => onChangeFilters({ ...filters, group_id: event.target.value })} />
          </label>
          <label>
            <span>日期</span>
            <input type="date" value={filters.date} onChange={(event) => onChangeFilters({ ...filters, date: event.target.value })} />
          </label>
          <div className="filter-actions">
            <button disabled={disabled} onClick={onApplyFilters} type="button">
              应用筛选
            </button>
            <button className="secondary" disabled={disabled} onClick={onClearFilters} type="button">
              清空
            </button>
            <button className="secondary" disabled={disabled} onClick={onRefresh} type="button">
              <RefreshCw size={16} />
              刷新
            </button>
          </div>
        </div>
      </Panel>

      <div className="replay-grid">
        <Panel title="卡咔回复列表" subtitle={`第 ${page} / ${totalPages} 页，当前 ${start}-${end} 条，共 ${total} 条。`}>
          <div className="control-bar replay-list-bar">
            <span className="selection-text">每页 {pageSize} 条，点击任一条查看复盘详情</span>
            <div className="toolbar-actions">
              <div className="pagination-controls" aria-label="对话复盘分页">
                <button
                  className="icon-button secondary"
                  disabled={disabled || page <= 1}
                  onClick={() => onChangePage(page - 1)}
                  title="上一页"
                  type="button"
                >
                  <ChevronLeft size={17} />
                </button>
                <span>
                  {page} / {totalPages}
                </span>
                <button
                  className="icon-button secondary"
                  disabled={disabled || page >= totalPages}
                  onClick={() => onChangePage(page + 1)}
                  title="下一页"
                  type="button"
                >
                  <ChevronRight size={17} />
                </button>
              </div>
            </div>
          </div>
          <div className="replay-table">
            <div className="replay-row replay-row-head">
              <span>编号</span>
              <span>用户消息 / 卡咔回复</span>
              <span>时间 / 对象</span>
              <span>命中概况</span>
            </div>
            {conversations.map((conversation) => {
              const metadata = conversationMetadata(conversation);
              const replyState = conversation.reply_state;
              return (
                <button
                  className={`replay-row ${selectedId === conversation.id ? "selected" : ""}`}
                  key={conversation.id}
                  onClick={() => onOpenDetail(conversation.id)}
                  type="button"
                >
                  <span className="replay-row-id">
                    <strong>#{conversation.id}</strong>
                    <span className={`badge ${replyStateClass(replyState)}`}>{replyStateLabel(replyState)}</span>
                  </span>
                  <span className="replay-row-main">
                    <strong>{conversation.content_text || "-"}</strong>
                    <small>{conversation.output?.content_text || "回复内容缺失"}</small>
                  </span>
                  <span className="replay-row-meta">
                    <strong>{conversation.created_at}</strong>
                    <small>{formatUser(conversation.user)} / {formatScene(conversation.scene)}</small>
                  </span>
                  <span className="replay-row-stats">
                    关系 {metadataText(metadata, "relationship_level")} / 记忆 {metadataNumber(metadata, "memory_count")} / 短期{" "}
                    {metadataNumber(metadata, "short_context_count")}
                  </span>
                </button>
              );
            })}
            {!conversations.length && <EmptyState message="暂无卡咔回复记录" />}
          </div>
        </Panel>

        <Panel title="回复复盘" subtitle="回查真实发生过的回复，查看当时实际使用的记忆、短期上下文和 metadata。">
          {detail ? (
            <div className="replay-detail">
              <KeyValueGrid
                data={{
                  输入编号: detail.conversation.id,
                  回复状态: replyStateLabel(detail.conversation.reply_state),
                  触发原因: metadataText(detailMetadata, "output_reason", detail.conversation.output?.output_reason || "-"),
                  输出来源: metadataText(detailMetadata, "output_origin", detail.conversation.output?.output_origin || "-"),
                  模型: metadataText(detailMetadata, "llm_model"),
                  关系: metadataText(detailMetadata, "relationship_level"),
                  命中记忆: metadataNumber(detailMetadata, "memory_count"),
                  短期上下文: metadataNumber(detailMetadata, "short_context_count"),
                  记忆编号: detail.used_memory_ids.length ? detail.used_memory_ids.join("、") : "-",
                  上下文编号: detail.short_context_input_ids.length ? detail.short_context_input_ids.join("、") : "-"
                }}
              />
              <div className="replay-message-grid">
                <PromptBlock title="用户消息" content={detail.conversation.content_text || "-"} />
                <PromptBlock title="卡咔回复" content={detail.conversation.output?.content_text || "-"} />
              </div>
              <PromptBlock title="输出 Metadata" content={JSON.stringify(detailMetadata, null, 2)} />

              <div className="replay-evidence-grid">
                <section className="replay-section">
                  <div className="replay-section-head">
                    <h3>短期上下文</h3>
                    <span>来自 outputs.metadata.short_context_input_ids</span>
                  </div>
                  <div className="result-list">
                    {detail.short_context.map((item) => (
                      <article className="result-item" key={item.id}>
                        <div className="result-head">
                          <strong>#{item.id} / {formatUser(item.user)}</strong>
                          <span className="score-badge">{replyStateLabel(item.reply_state)}</span>
                        </div>
                        <p>{item.content_text || "-"}</p>
                        <small>{item.created_at} / {formatScene(item.scene)}</small>
                        {item.output?.content_text && <small>卡咔：{item.output.content_text}</small>}
                      </article>
                    ))}
                    {!detail.short_context.length && <EmptyState message="这次回复没有短期上下文" />}
                  </div>
                </section>

                <section className="replay-section">
                  <div className="replay-section-head">
                    <h3>命中的正式记忆</h3>
                    <span>来自 outputs.metadata.used_memory_ids</span>
                  </div>
                  <div className="result-list">
                    {detail.used_memories.map((memory) => (
                      <article className="result-item" key={memory.id}>
                        <div className="result-head">
                          <strong>#{memory.id} / {memoryTypeLabel(memory.memory_type || "-")}</strong>
                          <span className="score-badge">{memory.status}</span>
                        </div>
                        <p>{memory.memory_text}</p>
                        <small>{formatUser(memory.user)} / {formatScene(memory.scene)}</small>
                      </article>
                    ))}
                    {!detail.used_memories.length && <EmptyState message="这次回复没有命中正式记忆" />}
                  </div>
                </section>
              </div>
            </div>
          ) : (
            <EmptyState message="从左侧列表选择一条卡咔回复，查看完整复盘。" />
          )}
        </Panel>
      </div>
    </section>
  );
}

function PromptBlock({ title, content }: { title: string; content: string }) {
  return (
    <article className="prompt-block">
      <div className="prompt-title">{title}</div>
      <pre>{content || "-"}</pre>
    </article>
  );
}

function StatusPage({
  autoJobRuns,
  counts,
  disabled,
  settings,
  serverTime,
  onTriggerAutoJob
}: {
  autoJobRuns: AutoJobRun[];
  counts: Record<string, number>;
  disabled: boolean;
  settings: Summary["settings"];
  serverTime: string;
  onTriggerAutoJob: (jobName: AutoJobName) => void;
}) {
  const notAnalyzedInputs = counts.not_analyzed_inputs ?? 0;
  const pendingCandidates = counts.pending_candidates ?? 0;
  const analysisThreshold = numberSetting(settings, "memory_auto_analysis_trigger_count", 50);
  const analysisBatchLimit = numberSetting(settings, "memory_auto_analysis_batch_limit", 50);
  const analysisMaxRuns = numberSetting(settings, "memory_auto_analysis_max_runs_per_check", 1);
  const analysisIntervalSeconds = numberSetting(settings, "memory_auto_analysis_interval_seconds", 0);
  const reviewThreshold = numberSetting(settings, "memory_auto_review_trigger_count", 20);
  const reviewBatchSize = numberSetting(settings, "memory_auto_review_batch_size", 10);
  const reviewMaxRuns = numberSetting(settings, "memory_auto_review_max_runs_per_check", 1);

  return (
    <div className="page-stack">
      <section className="stats-grid">
        <Metric icon={Brain} title="使用中记忆" value={counts.active_memories ?? counts.memories ?? 0} />
        <Metric icon={Archive} title="已归档" value={counts.archived_memories ?? 0} />
        <Metric icon={ShieldCheck} title="待分析输入" value={notAnalyzedInputs} />
        <Metric icon={CheckCircle2} title="待复核候选" value={pendingCandidates} />
      </section>
      <Panel title="当前处理队列" subtitle="这里显示当前数据库状态，和下面的历史运行快照分开看">
        <div className="job-queue-grid">
          <div className="job-queue-item">
            <div className="job-queue-head">
              <div>
                <strong>自动候选分析</strong>
                <span>not_analyzed 输入</span>
              </div>
              <span className={`queue-state ${notAnalyzedInputs >= analysisThreshold ? "ready" : "waiting"}`}>
                {queueStateLabel(notAnalyzedInputs, analysisThreshold)}
              </span>
            </div>
            <KeyValueGrid
              data={{
                当前数量: notAnalyzedInputs,
                触发门槛: analysisThreshold,
                检查节奏: formatIntervalSeconds(analysisIntervalSeconds),
                单次上限: `${analysisBatchLimit} 条 × ${analysisMaxRuns} 轮`
              }}
            />
            <div className="job-actions">
              <button disabled={disabled} onClick={() => onTriggerAutoJob("auto_analysis")} type="button">
                <RefreshCw size={15} />
                立即分析
              </button>
            </div>
          </div>
          <div className="job-queue-item">
            <div className="job-queue-head">
              <div>
                <strong>自动候选复核</strong>
                <span>pending 候选</span>
              </div>
              <span className={`queue-state ${pendingCandidates >= reviewThreshold ? "ready" : "waiting"}`}>
                {queueStateLabel(pendingCandidates, reviewThreshold)}
              </span>
            </div>
            <KeyValueGrid
              data={{
                当前数量: pendingCandidates,
                触发门槛: reviewThreshold,
                检查节奏: "整点检查",
                单次上限: `${reviewBatchSize} 条 × ${reviewMaxRuns} 轮`
              }}
            />
            <div className="job-actions">
              <button disabled={disabled} onClick={() => onTriggerAutoJob("auto_review")} type="button">
                <RefreshCw size={15} />
                立即复核
              </button>
            </div>
          </div>
        </div>
      </Panel>
      <Panel title="配置详情" subtitle="当前管理端读取到的关键配置">
        <KeyValueGrid
          data={{
            服务器时间: serverTime,
            远程模型: settingText(settings.llm_enabled),
            自动分析: settingText(settings.memory_auto_analysis_enabled),
            分析触发门槛: `${analysisThreshold} 条`,
            分析检查节奏: formatIntervalSeconds(analysisIntervalSeconds),
            自动复核: settingText(settings.memory_auto_review_enabled),
            复核触发门槛: `${reviewThreshold} 条`,
            回复注入: settingText(settings.memory_reply_injection_enabled),
            注入条数: settingText(settings.memory_reply_limit, "0"),
            最低分: settingText(settings.memory_reply_min_score, "0"),
            本地管理: settingText(settings.admin_local_only),
            "API Token": settings.admin_api_token_configured ? "已配置" : "未配置"
          }}
        />
      </Panel>
      <Panel title="自动任务运行记录" subtitle="历史快照：检查数是当次运行看到的数量，不代表当前队列数量">
        {autoJobRuns.length ? (
          <div className="result-list">
            {autoJobRuns.map((run) => (
              <article className="result-item" key={run.id}>
                <div className="result-head">
                  <strong>
                    #{run.id} / {run.job_label}
                  </strong>
                  <span className={`score-badge ${autoJobStatusClass(run.status)}`}>{run.status_label}</span>
                </div>
                <p>{run.reason}</p>
                <small>
                  完成 {run.finished_at} / 当时检查 {run.checked_count} / 轮数 {run.processed_runs} / 新增{" "}
                  {run.inserted_count} / 更新 {run.updated_count} / 标记跳过 {run.skipped_count} / 错误{" "}
                  {run.error_count} / {run.duration_seconds.toFixed(1)} 秒
                </small>
                <small>{currentQueueLabelForJob(run.job_name, counts)}</small>
                {run.error_message && <small>{run.error_message}</small>}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState message="暂无自动任务运行记录" />
        )}
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
