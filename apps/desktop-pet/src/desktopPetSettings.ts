export type IdleSleepDelayMs = 60_000 | 120_000 | 300_000 | null;

export type DesktopPetSettings = {
  debugStateMenuEnabled: boolean;
  idleAmbientEnabled: boolean;
  idleSleepDelayMs: IdleSleepDelayMs;
};

export const WINDOW_POSITION_STORAGE_KEY = "kaka.desktopPet.windowPosition";
export const DESKTOP_PET_SETTINGS_STORAGE_KEY = "kaka.desktopPet.settings";
export const SETTINGS_UPDATED_EVENT = "kaka-settings-updated";
export const TRAY_EVENT_RESET_POSITION = "kaka-tray-reset-position";
export const TRAY_EVENT_CHECK_CORE = "kaka-tray-check-core";

export const DEFAULT_DESKTOP_PET_SETTINGS: DesktopPetSettings = {
  debugStateMenuEnabled: false,
  idleAmbientEnabled: true,
  idleSleepDelayMs: 120_000
};

const VALID_SLEEP_DELAYS: readonly IdleSleepDelayMs[] = [60_000, 120_000, 300_000, null];

export function readDesktopPetSettings(): DesktopPetSettings {
  try {
    const rawValue = window.localStorage.getItem(DESKTOP_PET_SETTINGS_STORAGE_KEY);
    if (!rawValue) return DEFAULT_DESKTOP_PET_SETTINGS;

    const parsedValue = JSON.parse(rawValue) as Partial<DesktopPetSettings>;
    const idleSleepDelayMs = VALID_SLEEP_DELAYS.includes(parsedValue.idleSleepDelayMs as IdleSleepDelayMs)
      ? (parsedValue.idleSleepDelayMs as IdleSleepDelayMs)
      : DEFAULT_DESKTOP_PET_SETTINGS.idleSleepDelayMs;

    return {
      debugStateMenuEnabled:
        typeof parsedValue.debugStateMenuEnabled === "boolean"
          ? parsedValue.debugStateMenuEnabled
          : DEFAULT_DESKTOP_PET_SETTINGS.debugStateMenuEnabled,
      idleAmbientEnabled:
        typeof parsedValue.idleAmbientEnabled === "boolean"
          ? parsedValue.idleAmbientEnabled
          : DEFAULT_DESKTOP_PET_SETTINGS.idleAmbientEnabled,
      idleSleepDelayMs
    };
  } catch {
    return DEFAULT_DESKTOP_PET_SETTINGS;
  }
}

export function writeDesktopPetSettings(settings: DesktopPetSettings) {
  window.localStorage.setItem(DESKTOP_PET_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
}
