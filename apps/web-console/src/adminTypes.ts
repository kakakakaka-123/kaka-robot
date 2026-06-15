export type Summary = {
  counts: Record<string, number>;
  memory_statuses: Record<string, number>;
  recent_auto_job_runs: AutoJobRun[];
  settings: Record<string, string | number | boolean | null | undefined>;
  server_time: string;
};

export type AutoJobRun = {
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

export type AutoJobName = "auto_analysis" | "auto_review";

export type AutoJobTriggerSummary = {
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

export type AutoJobTriggerResponse = {
  job_name: AutoJobName;
  job_label: string;
  force: boolean;
  summary: AutoJobTriggerSummary;
  latest_run?: AutoJobRun | null;
};

export type UserInfo = {
  platform_user_id: string;
  display_name: string;
};

export type SceneInfo = {
  scene_type: string;
  scene_type_label: string;
  scene_id: string;
};

export type Memory = {
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

export type SearchResult = {
  memory: Memory;
  scene?: SceneInfo | null;
  score: number;
  matched_terms: string[];
  reasons: string[];
};

export type ReplyContextMessage = {
  role: string;
  content: string;
};

export type ReplyContextLayer = {
  name: string;
  title: string;
  role: string;
  content: string;
};

export type ReplyContextPreview = {
  messages: ReplyContextMessage[];
  layers: ReplyContextLayer[];
  metadata: Record<string, unknown>;
  used_memory_ids: number[];
  memory_count: number;
  memory_injection_enabled: boolean;
};

export type OutputInfo = {
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

export type Conversation = {
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

export type ConversationDetail = {
  conversation: Conversation;
  metadata: Record<string, unknown>;
  used_memory_ids: number[];
  used_memories: Memory[];
  short_context_input_ids: number[];
  short_context: Conversation[];
};

export type SearchForm = {
  user_id: string;
  group_id: string;
  text: string;
  private: boolean;
  min_score: number;
};

export type ConversationFilters = {
  ids: string;
  user_id: string;
  group_id: string;
  date: string;
  reply_state: string;
};

export type MemoryFilters = {
  ids: string;
  user_id: string;
  group_id: string;
  date: string;
  memory_type: string;
};

export type MemoryForm = {
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

export type MemoryStatusFilter = "active" | "archived" | "all";
export type PageKey = "overview" | "memories" | "prompt" | "replay" | "status" | "reserved";
export type ThemeMode = "light" | "dark";
