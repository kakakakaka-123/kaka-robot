export type IdleSleepDelayMs = 60_000 | 120_000 | 300_000 | null;
export type IdleAmbientFrequency = "low" | "normal" | "high";
export type PetWindowSizePx = 240 | 280 | 320;
export type SpeechBubbleDurationMs = 1800 | 2600 | 4000;

export type DesktopPetSettings = {
  alwaysOnTopEnabled: boolean;
  speechBubbleDurationMs: SpeechBubbleDurationMs;
  debugStateMenuEnabled: boolean;
  idleAmbientEnabled: boolean;
  idleAmbientFrequency: IdleAmbientFrequency;
  idleSleepDelayMs: IdleSleepDelayMs;
  petWindowSizePx: PetWindowSizePx;
  showStateLabel: boolean;
};

export const WINDOW_POSITION_STORAGE_KEY = "kaka.desktopPet.windowPosition";
export const DESKTOP_PET_SETTINGS_STORAGE_KEY = "kaka.desktopPet.settings";
export const SETTINGS_UPDATED_EVENT = "kaka-settings-updated";
export const TRAY_EVENT_RESET_POSITION = "kaka-tray-reset-position";
export const TRAY_EVENT_CHECK_CORE = "kaka-tray-check-core";

export const DEFAULT_DESKTOP_PET_SETTINGS: DesktopPetSettings = {
  alwaysOnTopEnabled: true,
  speechBubbleDurationMs: 2600,
  debugStateMenuEnabled: false,
  idleAmbientEnabled: true,
  idleAmbientFrequency: "normal",
  idleSleepDelayMs: 120_000,
  petWindowSizePx: 280,
  showStateLabel: true
};

const VALID_SLEEP_DELAYS: readonly IdleSleepDelayMs[] = [60_000, 120_000, 300_000, null];
const VALID_IDLE_AMBIENT_FREQUENCIES: readonly IdleAmbientFrequency[] = ["low", "normal", "high"];
const VALID_PET_WINDOW_SIZES: readonly PetWindowSizePx[] = [240, 280, 320];
const VALID_SPEECH_BUBBLE_DURATIONS: readonly SpeechBubbleDurationMs[] = [1800, 2600, 4000];

export function readDesktopPetSettings(): DesktopPetSettings {
  try {
    const rawValue = window.localStorage.getItem(DESKTOP_PET_SETTINGS_STORAGE_KEY);
    if (!rawValue) return DEFAULT_DESKTOP_PET_SETTINGS;

    const parsedValue = JSON.parse(rawValue) as Partial<DesktopPetSettings>;
    const idleSleepDelayMs = VALID_SLEEP_DELAYS.includes(parsedValue.idleSleepDelayMs as IdleSleepDelayMs)
      ? (parsedValue.idleSleepDelayMs as IdleSleepDelayMs)
      : DEFAULT_DESKTOP_PET_SETTINGS.idleSleepDelayMs;
    const idleAmbientFrequency = VALID_IDLE_AMBIENT_FREQUENCIES.includes(
      parsedValue.idleAmbientFrequency as IdleAmbientFrequency
    )
      ? (parsedValue.idleAmbientFrequency as IdleAmbientFrequency)
      : DEFAULT_DESKTOP_PET_SETTINGS.idleAmbientFrequency;
    const petWindowSizePx = VALID_PET_WINDOW_SIZES.includes(parsedValue.petWindowSizePx as PetWindowSizePx)
      ? (parsedValue.petWindowSizePx as PetWindowSizePx)
      : DEFAULT_DESKTOP_PET_SETTINGS.petWindowSizePx;
    const speechBubbleDurationMs = VALID_SPEECH_BUBBLE_DURATIONS.includes(
      parsedValue.speechBubbleDurationMs as SpeechBubbleDurationMs
    )
      ? (parsedValue.speechBubbleDurationMs as SpeechBubbleDurationMs)
      : DEFAULT_DESKTOP_PET_SETTINGS.speechBubbleDurationMs;

    return {
      alwaysOnTopEnabled:
        typeof parsedValue.alwaysOnTopEnabled === "boolean"
          ? parsedValue.alwaysOnTopEnabled
          : DEFAULT_DESKTOP_PET_SETTINGS.alwaysOnTopEnabled,
      speechBubbleDurationMs,
      debugStateMenuEnabled:
        typeof parsedValue.debugStateMenuEnabled === "boolean"
          ? parsedValue.debugStateMenuEnabled
          : DEFAULT_DESKTOP_PET_SETTINGS.debugStateMenuEnabled,
      idleAmbientEnabled:
        typeof parsedValue.idleAmbientEnabled === "boolean"
          ? parsedValue.idleAmbientEnabled
          : DEFAULT_DESKTOP_PET_SETTINGS.idleAmbientEnabled,
      idleAmbientFrequency,
      idleSleepDelayMs,
      petWindowSizePx,
      showStateLabel:
        typeof parsedValue.showStateLabel === "boolean"
          ? parsedValue.showStateLabel
          : DEFAULT_DESKTOP_PET_SETTINGS.showStateLabel
    };
  } catch {
    return DEFAULT_DESKTOP_PET_SETTINGS;
  }
}

export function writeDesktopPetSettings(settings: DesktopPetSettings) {
  window.localStorage.setItem(DESKTOP_PET_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
}
