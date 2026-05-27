import { invoke } from "@tauri-apps/api/core";
import { emit } from "@tauri-apps/api/event";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  type DesktopPetSettings,
  type IdleSleepDelayMs,
  readDesktopPetSettings,
  SETTINGS_UPDATED_EVENT,
  TRAY_EVENT_RESET_POSITION,
  WINDOW_POSITION_STORAGE_KEY,
  writeDesktopPetSettings
} from "./desktopPetSettings";

type CoreStatus = "unknown" | "checking" | "ok" | "failed";

const SLEEP_DELAY_OPTIONS: Array<{ label: string; value: IdleSleepDelayMs }> = [
  { label: "1 分钟", value: 60_000 },
  { label: "2 分钟", value: 120_000 },
  { label: "5 分钟", value: 300_000 },
  { label: "不自动睡觉", value: null }
];

function sleepDelayToInputValue(value: IdleSleepDelayMs): string {
  return value === null ? "off" : String(value);
}

function inputValueToSleepDelay(value: string): IdleSleepDelayMs {
  if (value === "60000") return 60_000;
  if (value === "120000") return 120_000;
  if (value === "300000") return 300_000;
  return null;
}

export function SettingsApp() {
  const [settings, setSettings] = useState<DesktopPetSettings>(() => readDesktopPetSettings());
  const [autostartEnabled, setAutostartEnabled] = useState(false);
  const [coreStatus, setCoreStatus] = useState<CoreStatus>("unknown");
  const [message, setMessage] = useState("");

  const coreStatusText = useMemo(() => {
    if (coreStatus === "checking") return "检查中";
    if (coreStatus === "ok") return "核心信号正常";
    if (coreStatus === "failed") return "信号弱";
    return "未检查";
  }, [coreStatus]);

  const refreshAutostart = useCallback(async () => {
    try {
      const enabled = await invoke<boolean>("get_autostart_enabled");
      setAutostartEnabled(enabled);
    } catch {
      setMessage("读取开机自启状态失败。");
    }
  }, []);

  const persistSettings = useCallback(async (nextSettings: DesktopPetSettings) => {
    setSettings(nextSettings);
    writeDesktopPetSettings(nextSettings);
    await emit(SETTINGS_UPDATED_EVENT);
  }, []);

  const toggleAutostart = useCallback(async () => {
    try {
      const enabled = await invoke<boolean>("set_autostart_enabled", { enabled: !autostartEnabled });
      setAutostartEnabled(enabled);
      setMessage(enabled ? "已开启开机自启。" : "已关闭开机自启。");
    } catch {
      setMessage("开机自启切换失败。");
    }
  }, [autostartEnabled]);

  const testCoreConnection = useCallback(async () => {
    setCoreStatus("checking");
    setMessage("正在检查核心信号...");
    try {
      await invoke("check_kaka_core_health");
      setCoreStatus("ok");
      setMessage("核心信号正常。");
    } catch {
      setCoreStatus("failed");
      setMessage("信号有点弱，核心大脑没连上。");
    }
  }, []);

  const resetWindowPosition = useCallback(async () => {
    try {
      window.localStorage.removeItem(WINDOW_POSITION_STORAGE_KEY);
      await invoke("center_main_window");
      await emit(TRAY_EVENT_RESET_POSITION);
      setMessage("卡咔回到屏幕中间了。");
    } catch {
      setMessage("位置重置失败了。");
    }
  }, []);

  useEffect(() => {
    void refreshAutostart();
  }, [refreshAutostart]);

  return (
    <main className="settings-shell">
      <header className="settings-header">
        <div>
          <h1>卡咔设置</h1>
          <p>常驻桌宠控制</p>
        </div>
        <div className="settings-status-pill">{coreStatusText}</div>
      </header>

      <section className="settings-section">
        <h2>状态</h2>
        <div className="settings-row">
          <span>开机自启</span>
          <strong>{autostartEnabled ? "已开启" : "未开启"}</strong>
        </div>
        <div className="settings-row">
          <span>核心连接</span>
          <strong>{coreStatusText}</strong>
        </div>
      </section>

      <section className="settings-section">
        <h2>常用操作</h2>
        <div className="settings-actions">
          <button type="button" onClick={() => void toggleAutostart()}>
            {autostartEnabled ? "关闭开机自启" : "开启开机自启"}
          </button>
          <button type="button" onClick={() => void testCoreConnection()}>
            连接测试
          </button>
          <button type="button" onClick={() => void resetWindowPosition()}>
            重置位置
          </button>
        </div>
      </section>

      <section className="settings-section">
        <h2>行为</h2>
        <label className="settings-toggle">
          <input
            type="checkbox"
            checked={settings.idleAmbientEnabled}
            onChange={(event) =>
              void persistSettings({
                ...settings,
                idleAmbientEnabled: event.currentTarget.checked
              })
            }
          />
          <span>启用随机待机气泡和小动作</span>
        </label>

        <label className="settings-field">
          <span>闲置睡觉时间</span>
          <select
            value={sleepDelayToInputValue(settings.idleSleepDelayMs)}
            onChange={(event) =>
              void persistSettings({
                ...settings,
                idleSleepDelayMs: inputValueToSleepDelay(event.currentTarget.value)
              })
            }
          >
            {SLEEP_DELAY_OPTIONS.map((option) => (
              <option key={sleepDelayToInputValue(option.value)} value={sleepDelayToInputValue(option.value)}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </section>

      {message && <div className="settings-message">{message}</div>}
    </main>
  );
}
