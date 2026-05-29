import type { PetStateId } from "./petStates";

const MAX_REPLY_SEGMENT_LENGTH = 58;
const MAX_REPLY_CONTENT_SEGMENTS = 3;
const CHAT_REPLY_TRUNCATED_NOTICE = "后面还有一点，卡咔先说这些。";

const THINKING_KEYWORDS = [
  "我想想",
  "想一下",
  "可能",
  "大概",
  "我觉得",
  "看起来",
  "需要",
  "分析",
  "原因",
  "因为",
  "建议",
  "如果",
  "可以先",
  "步骤"
];

const HAPPY_KEYWORDS = [
  "好呀",
  "可以",
  "没问题",
  "太好了",
  "开心",
  "可爱",
  "喜欢",
  "嘿嘿",
  "喵",
  "成功",
  "放心",
  "不错",
  "搞定"
];

export function normalizeChatReplyText(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

export function getChatReplyState(replyText: string): PetStateId {
  const normalizedText = normalizeChatReplyText(replyText);
  if (!normalizedText) return "message";

  if (THINKING_KEYWORDS.some((keyword) => normalizedText.includes(keyword))) {
    return "thinking";
  }

  if (HAPPY_KEYWORDS.some((keyword) => normalizedText.includes(keyword))) {
    return "happy";
  }

  if (normalizedText.length > 80) {
    return "thinking";
  }

  return "message";
}

export function getChatFailureBubbleText(error: unknown): string {
  const errorText = String(error ?? "").toLowerCase();

  if (
    errorText.includes("connect failed") ||
    errorText.includes("connection refused") ||
    errorText.includes("无法连接") ||
    errorText.includes("由于目标计算机积极拒绝")
  ) {
    return "核心信号没接上。";
  }

  if (
    errorText.includes("timed out") ||
    errorText.includes("timeout") ||
    errorText.includes("超时") ||
    errorText.includes("操作超时")
  ) {
    return "卡咔想太久了，信号可能卡住了。";
  }

  if (
    errorText.includes("invalid chat response json") ||
    errorText.includes("chat response has no text action") ||
    errorText.includes("chat response has no actions") ||
    errorText.includes("unexpected http status")
  ) {
    return "卡咔听到了，但回复卡住了。";
  }

  return "信号有点弱，卡咔没接到核心回复。";
}

export function getChatBubbleDurationMs(text: string, baseDurationMs: number): number {
  const normalizedText = normalizeChatReplyText(text);
  const calculatedDurationMs = 2600 + normalizedText.length * 58;
  return Math.min(7600, Math.max(baseDurationMs, calculatedDurationMs));
}

export function splitChatReplyIntoBubbles(replyText: string): string[] {
  const normalizedText = normalizeChatReplyText(replyText);
  if (!normalizedText) return ["卡咔听到了。"];

  const contentSegments = buildReplySegments(normalizedText);
  if (contentSegments.length <= MAX_REPLY_CONTENT_SEGMENTS) {
    return contentSegments;
  }

  return [...contentSegments.slice(0, MAX_REPLY_CONTENT_SEGMENTS), CHAT_REPLY_TRUNCATED_NOTICE];
}

function buildReplySegments(text: string): string[] {
  const sentencePieces = text.match(/[^。！？!?；;…]+[。！？!?；;…]*/g) ?? [text];
  const segments: string[] = [];

  for (const piece of sentencePieces.flatMap(splitLongReplyPiece)) {
    const trimmedPiece = piece.trim();
    if (!trimmedPiece) continue;

    const previousSegment = segments[segments.length - 1];
    if (previousSegment && previousSegment.length + trimmedPiece.length <= MAX_REPLY_SEGMENT_LENGTH) {
      segments[segments.length - 1] = `${previousSegment}${trimmedPiece}`;
    } else {
      segments.push(trimmedPiece);
    }
  }

  return segments.length > 0 ? segments : [text];
}

function splitLongReplyPiece(piece: string): string[] {
  if (piece.length <= MAX_REPLY_SEGMENT_LENGTH) return [piece];

  const softPieces = piece.match(/[^，,、：:]+[，,、：:]*/g) ?? [piece];
  const result: string[] = [];
  let currentPiece = "";

  for (const softPiece of softPieces) {
    if (currentPiece.length + softPiece.length <= MAX_REPLY_SEGMENT_LENGTH) {
      currentPiece += softPiece;
      continue;
    }

    if (currentPiece) {
      result.push(currentPiece);
      currentPiece = "";
    }

    if (softPiece.length <= MAX_REPLY_SEGMENT_LENGTH) {
      currentPiece = softPiece;
    } else {
      result.push(...splitByLength(softPiece, MAX_REPLY_SEGMENT_LENGTH));
    }
  }

  if (currentPiece) {
    result.push(currentPiece);
  }

  return result;
}

function splitByLength(text: string, length: number): string[] {
  const result: string[] = [];
  for (let index = 0; index < text.length; index += length) {
    result.push(text.slice(index, index + length));
  }
  return result;
}
