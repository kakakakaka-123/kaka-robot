import type { PetStateId } from "./petStates";

export type PetBehaviorReaction = {
  stateId?: PetStateId;
  text: string;
  durationMs: number;
};

export type PetBehaviorMemory = {
  cooldownUntilByKey: Record<string, number>;
  lastBubbleText: string | null;
  lastTouchAt: number;
  sleepCooldownUntil: number;
  touchStreak: number;
};

type WeightedBehaviorReaction = PetBehaviorReaction & {
  key: string;
  weight: number;
  cooldownMs?: number;
  maxTouchStreak?: number;
  minTouchStreak?: number;
};

const TOUCH_STREAK_WINDOW_MS = 5200;
const WAKE_SLEEP_COOLDOWN_MS = 25 * 1000;

const STATE_BUBBLE_TEXT: Partial<Record<PetStateId, string>> = {
  idle: "我在这儿。",
  happy: "今天心情不错！",
  sleepy: "有点困困的...",
  thinking: "让我想一想。",
  angry: "哼，卡咔炸毛了！",
  dead404: "卡咔暂时离线。",
  message: "收到新消息了。",
  sleep: "我先睡一会儿...",
  pet: "嘿嘿，再摸一下。",
  loading: "卡咔加载中...",
  weakSignal: "信号有点弱。"
};

const IDLE_AMBIENT_REACTIONS: readonly WeightedBehaviorReaction[] = [
  { key: "idle-bubble-here", text: "我还在这里。", durationMs: 2600, weight: 4, cooldownMs: 20 * 1000 },
  { key: "idle-bubble-calm", text: "桌面风平浪静。", durationMs: 2600, weight: 3, cooldownMs: 20 * 1000 },
  { key: "idle-bubble-patrol", text: "卡咔巡视中。", durationMs: 2600, weight: 3, cooldownMs: 24 * 1000 },
  { key: "idle-bubble-running", text: "今天也要好好运行。", durationMs: 2600, weight: 2, cooldownMs: 24 * 1000 },
  { key: "idle-bubble-touch", text: "有事可以摸摸我。", durationMs: 2600, weight: 2, cooldownMs: 28 * 1000 },
  { key: "idle-bubble-standby", text: "我在旁边待机。", durationMs: 2600, weight: 3, cooldownMs: 20 * 1000 },
  {
    key: "idle-action-happy",
    stateId: "happy",
    text: "今天心情不错！",
    durationMs: 3200,
    weight: 2,
    cooldownMs: 18 * 1000
  },
  {
    key: "idle-action-thinking",
    stateId: "thinking",
    text: "让我想一想。",
    durationMs: 4200,
    weight: 2,
    cooldownMs: 22 * 1000
  },
  {
    key: "idle-action-sleepy",
    stateId: "sleepy",
    text: "有点困困的...",
    durationMs: 5200,
    weight: 1,
    cooldownMs: 30 * 1000
  }
] as const;

const TOUCH_REACTIONS: readonly WeightedBehaviorReaction[] = [
  {
    key: "touch-pet-again",
    stateId: "pet",
    text: "嘿嘿，再摸一下。",
    durationMs: 2100,
    weight: 5,
    maxTouchStreak: 2
  },
  {
    key: "touch-happy-cache",
    stateId: "happy",
    text: "收到摸头，心情加一格。",
    durationMs: 2400,
    weight: 4,
    maxTouchStreak: 3
  },
  {
    key: "touch-tail",
    stateId: "pet",
    text: "尾巴要藏好。",
    durationMs: 2200,
    weight: 3,
    maxTouchStreak: 3
  },
  {
    key: "touch-thinking-cache",
    stateId: "thinking",
    text: "摸头会提高缓存命中率吗...",
    durationMs: 2600,
    weight: 2,
    maxTouchStreak: 3
  },
  {
    key: "touch-allowed",
    stateId: "happy",
    text: "今天允许你多摸两下。",
    durationMs: 2400,
    weight: 3,
    minTouchStreak: 2,
    maxTouchStreak: 4
  },
  {
    key: "touch-streak-noted",
    stateId: "happy",
    text: "连续摸头已记录，卡咔心情上升。",
    durationMs: 2600,
    weight: 4,
    minTouchStreak: 3,
    maxTouchStreak: 5,
    cooldownMs: 2600
  },
  {
    key: "touch-too-much-hair",
    stateId: "angry",
    text: "摸太多了，卡咔要整理发型。",
    durationMs: 2800,
    weight: 4,
    minTouchStreak: 5,
    cooldownMs: 7000
  },
  {
    key: "touch-too-much-buffer",
    stateId: "thinking",
    text: "再摸下去，缓存都要过热了。",
    durationMs: 2800,
    weight: 3,
    minTouchStreak: 5,
    cooldownMs: 7000
  }
] as const;

const DOUBLE_TOUCH_REACTIONS: readonly WeightedBehaviorReaction[] = [
  {
    key: "double-touch-confirm",
    stateId: "happy",
    text: "双击收到，卡咔确认在线。",
    durationMs: 2600,
    weight: 4,
    cooldownMs: 2500
  },
  {
    key: "double-touch-fast",
    stateId: "pet",
    text: "这么快？卡咔差点没反应过来。",
    durationMs: 2800,
    weight: 3,
    cooldownMs: 3500
  },
  {
    key: "double-touch-ping",
    stateId: "message",
    text: "收到两次敲门，信号清楚。",
    durationMs: 2700,
    weight: 2,
    cooldownMs: 3500
  }
] as const;

const LONG_PRESS_REACTIONS: readonly WeightedBehaviorReaction[] = [
  {
    key: "long-press-question",
    stateId: "thinking",
    text: "按住不放，是在观察卡咔吗？",
    durationMs: 3000,
    weight: 4,
    cooldownMs: 5000
  },
  {
    key: "long-press-shy",
    stateId: "pet",
    text: "一直按着的话，卡咔会有点在意。",
    durationMs: 3200,
    weight: 3,
    cooldownMs: 6000
  },
  {
    key: "long-press-protest",
    stateId: "angry",
    text: "松手啦，发型要被按扁了。",
    durationMs: 3000,
    weight: 2,
    cooldownMs: 7000
  }
] as const;

const LONG_DRAG_REACTIONS: readonly WeightedBehaviorReaction[] = [
  {
    key: "long-drag-dizzy",
    stateId: "drag",
    text: "拖太久了，卡咔有点晕。",
    durationMs: 2600,
    weight: 4,
    cooldownMs: 9000
  },
  {
    key: "long-drag-route",
    stateId: "drag",
    text: "这是桌面环游路线吗？",
    durationMs: 2800,
    weight: 3,
    cooldownMs: 9000
  },
  {
    key: "long-drag-stop",
    stateId: "drag",
    text: "找好位置了吗，创造者大人。",
    durationMs: 2800,
    weight: 2,
    cooldownMs: 9000
  }
] as const;

const DRAG_END_REACTIONS: readonly WeightedBehaviorReaction[] = [
  { key: "drag-end-down", text: "放好啦。", durationMs: 2200, weight: 4 },
  { key: "drag-end-place", text: "这个位置也不错。", durationMs: 2400, weight: 3 },
  { key: "drag-end-stable", text: "卡咔已停稳。", durationMs: 2200, weight: 3 },
  { key: "drag-end-finally", text: "终于落地了。", durationMs: 2400, weight: 2, cooldownMs: 5000 }
] as const;

const WAKE_REACTIONS: readonly WeightedBehaviorReaction[] = [
  { key: "wake-up", text: "唔...我醒啦。", durationMs: 2600, weight: 4, cooldownMs: 5000 },
  { key: "wake-light", text: "刚才睡得很轻。", durationMs: 2600, weight: 3, cooldownMs: 5000 },
  { key: "wake-online", text: "卡咔重新上线。", durationMs: 2600, weight: 3, cooldownMs: 5000 }
] as const;

const SLEEP_REACTIONS: readonly WeightedBehaviorReaction[] = [
  { key: "sleep-rest", stateId: "sleep", text: "我先睡一会儿...", durationMs: 2600, weight: 4, cooldownMs: 10 * 1000 },
  { key: "sleep-soft", stateId: "sleep", text: "进入轻量睡眠模式。", durationMs: 2600, weight: 2, cooldownMs: 10 * 1000 }
] as const;

export function createPetBehaviorMemory(): PetBehaviorMemory {
  return {
    cooldownUntilByKey: {},
    lastBubbleText: null,
    lastTouchAt: 0,
    sleepCooldownUntil: 0,
    touchStreak: 0
  };
}

export function getStateBubbleText(stateId: PetStateId): string | undefined {
  return STATE_BUBBLE_TEXT[stateId];
}

export function getIdleAmbientReaction(memory: PetBehaviorMemory, now = getNowMs()): PetBehaviorReaction {
  return selectWeightedReaction(memory, IDLE_AMBIENT_REACTIONS, now);
}

export function getTouchReaction(memory: PetBehaviorMemory, now = getNowMs()): PetBehaviorReaction {
  const touchStreak = registerTouch(memory, now, 1);
  return selectWeightedReaction(memory, filterTouchReactions(TOUCH_REACTIONS, touchStreak), now);
}

export function getDoubleTouchReaction(memory: PetBehaviorMemory, now = getNowMs()): PetBehaviorReaction {
  registerTouch(memory, now, 2);
  return selectWeightedReaction(memory, DOUBLE_TOUCH_REACTIONS, now);
}

export function getLongPressReaction(memory: PetBehaviorMemory, now = getNowMs()): PetBehaviorReaction {
  return selectWeightedReaction(memory, LONG_PRESS_REACTIONS, now);
}

export function getLongDragReaction(memory: PetBehaviorMemory, now = getNowMs()): PetBehaviorReaction {
  return selectWeightedReaction(memory, LONG_DRAG_REACTIONS, now);
}

export function getDragEndReaction(memory: PetBehaviorMemory, now = getNowMs()): PetBehaviorReaction {
  return selectWeightedReaction(memory, DRAG_END_REACTIONS, now);
}

export function getWakeReaction(memory: PetBehaviorMemory, now = getNowMs()): PetBehaviorReaction {
  memory.sleepCooldownUntil = now + WAKE_SLEEP_COOLDOWN_MS;
  return selectWeightedReaction(memory, WAKE_REACTIONS, now);
}

export function getSleepReaction(memory: PetBehaviorMemory, now = getNowMs()): PetBehaviorReaction | null {
  if (memory.sleepCooldownUntil > now) return null;
  return selectWeightedReaction(memory, SLEEP_REACTIONS, now);
}

function filterTouchReactions(
  reactions: readonly WeightedBehaviorReaction[],
  touchStreak: number
): readonly WeightedBehaviorReaction[] {
  return reactions.filter((reaction) => {
    if (reaction.minTouchStreak !== undefined && touchStreak < reaction.minTouchStreak) return false;
    if (reaction.maxTouchStreak !== undefined && touchStreak > reaction.maxTouchStreak) return false;
    return true;
  });
}

function registerTouch(memory: PetBehaviorMemory, now: number, amount: number) {
  memory.touchStreak = now - memory.lastTouchAt <= TOUCH_STREAK_WINDOW_MS ? memory.touchStreak + amount : amount;
  memory.lastTouchAt = now;
  return memory.touchStreak;
}

function selectWeightedReaction(
  memory: PetBehaviorMemory,
  reactions: readonly WeightedBehaviorReaction[],
  now: number
): PetBehaviorReaction {
  const availableReactions = reactions.filter((reaction) => (memory.cooldownUntilByKey[reaction.key] ?? 0) <= now);
  const nonRepeatedReactions = availableReactions.filter((reaction) => reaction.text !== memory.lastBubbleText);
  const fallbackReactions = reactions.filter((reaction) => reaction.text !== memory.lastBubbleText);
  const pool =
    nonRepeatedReactions.length > 0
      ? nonRepeatedReactions
      : availableReactions.length > 0
        ? availableReactions
        : fallbackReactions.length > 0
          ? fallbackReactions
          : reactions;
  const selectedReaction = pickWeightedItem(pool);

  memory.lastBubbleText = selectedReaction.text;
  if (selectedReaction.cooldownMs) {
    memory.cooldownUntilByKey[selectedReaction.key] = now + selectedReaction.cooldownMs;
  }

  return {
    stateId: selectedReaction.stateId,
    text: selectedReaction.text,
    durationMs: selectedReaction.durationMs
  };
}

function pickWeightedItem<T extends { weight: number }>(items: readonly T[]): T {
  const totalWeight = items.reduce((total, item) => total + item.weight, 0);
  let cursor = getRandomFloat() * totalWeight;

  for (const item of items) {
    cursor -= item.weight;
    if (cursor <= 0) return item;
  }

  return items[items.length - 1];
}

function getRandomFloat() {
  const cryptoSource = globalThis.crypto;
  if (!cryptoSource) return Math.random();

  const value = new Uint32Array(1);
  cryptoSource.getRandomValues(value);
  return value[0] / (0xffffffff + 1);
}

function getNowMs() {
  return globalThis.performance?.now() ?? Date.now();
}
