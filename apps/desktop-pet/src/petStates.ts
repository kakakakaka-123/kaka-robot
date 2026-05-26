import angryUrl from "./assets/pet/angry.png";
import dead404Url from "./assets/pet/dead404.png";
import dragUrl from "./assets/pet/drag.png";
import happyUrl from "./assets/pet/happy.png";
import idleUrl from "./assets/pet/idle.png";
import loadingUrl from "./assets/pet/loading.png";
import messageUrl from "./assets/pet/message.png";
import petUrl from "./assets/pet/pet.png";
import sleepUrl from "./assets/pet/sleep.png";
import sleepyUrl from "./assets/pet/sleepy.png";
import thinkingUrl from "./assets/pet/thinking.png";
import weakSignalUrl from "./assets/pet/weak-signal.png";

export const PET_STATE_IDS = [
  "idle",
  "happy",
  "sleepy",
  "thinking",
  "angry",
  "dead404",
  "message",
  "sleep",
  "pet",
  "drag",
  "loading",
  "weakSignal"
] as const;

export type PetStateId = (typeof PET_STATE_IDS)[number];

export type PetStateConfig = {
  id: PetStateId;
  label: string;
  assetUrl: string;
  motion: "idle" | "bounce" | "drowsy" | "shake" | "sleep" | "drag" | "pulse";
};

export const PET_STATES: Record<PetStateId, PetStateConfig> = {
  idle: {
    id: "idle",
    label: "待机",
    assetUrl: idleUrl,
    motion: "idle"
  },
  happy: {
    id: "happy",
    label: "开心",
    assetUrl: happyUrl,
    motion: "bounce"
  },
  sleepy: {
    id: "sleepy",
    label: "困困",
    assetUrl: sleepyUrl,
    motion: "drowsy"
  },
  thinking: {
    id: "thinking",
    label: "思考",
    assetUrl: thinkingUrl,
    motion: "pulse"
  },
  angry: {
    id: "angry",
    label: "炸毛",
    assetUrl: angryUrl,
    motion: "shake"
  },
  dead404: {
    id: "dead404",
    label: "装死404",
    assetUrl: dead404Url,
    motion: "idle"
  },
  message: {
    id: "message",
    label: "收到消息",
    assetUrl: messageUrl,
    motion: "bounce"
  },
  sleep: {
    id: "sleep",
    label: "睡觉",
    assetUrl: sleepUrl,
    motion: "sleep"
  },
  pet: {
    id: "pet",
    label: "摸头反应",
    assetUrl: petUrl,
    motion: "pulse"
  },
  drag: {
    id: "drag",
    label: "拖拽反应",
    assetUrl: dragUrl,
    motion: "drag"
  },
  loading: {
    id: "loading",
    label: "加载中",
    assetUrl: loadingUrl,
    motion: "pulse"
  },
  weakSignal: {
    id: "weakSignal",
    label: "信号弱",
    assetUrl: weakSignalUrl,
    motion: "shake"
  }
};

export const PET_STATE_OPTIONS = PET_STATE_IDS.map((id) => PET_STATES[id]);
