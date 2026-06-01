import type { PetStateId } from "./petStates";

export type PetStateSource =
  | "idle"
  | "ambient"
  | "sleep"
  | "manual"
  | "reaction"
  | "chatReply"
  | "system"
  | "conversation"
  | "drag";

export type StoredWindowPosition = {
  x: number;
  y: number;
};

export function readStoredWindowPosition(storageKey: string): StoredWindowPosition | null {
  try {
    const rawValue = window.localStorage.getItem(storageKey);
    if (!rawValue) return null;

    const parsedValue = JSON.parse(rawValue) as Partial<StoredWindowPosition>;
    if (!isValidWindowCoordinate(parsedValue.x) || !isValidWindowCoordinate(parsedValue.y)) return null;

    return {
      x: Math.round(parsedValue.x),
      y: Math.round(parsedValue.y)
    };
  } catch {
    return null;
  }
}

export function isValidWindowCoordinate(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && Math.abs(value) < 100000;
}

export function getRandomInt(min: number, max: number): number {
  return Math.floor(window.crypto.getRandomValues(new Uint32Array(1))[0] / (0xffffffff + 1) * (max - min + 1)) + min;
}

export function getStableStateAfterDrag(stateId: PetStateId, source: PetStateSource): PetStateId {
  if (source === "manual" && stateId !== "drag") return stateId;
  return "idle";
}
