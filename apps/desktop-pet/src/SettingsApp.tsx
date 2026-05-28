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
type FeedbackTone = "info" | "success" | "error";
type PendingAction = "autostart" | "startup" | "core" | "reset" | null;

type StartupSettings = {
  showPetOnAutostart: boolean;
};

type FeedbackMessage = {
  tone: FeedbackTone;
  text: string;
};

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
  const [startupSettings, setStartupSettings] = useState<StartupSettings>({ showPetOnAutostart: false });
  const [autostartEnabled, setAutostartEnabled] = useState(false);
  const [coreStatus, setCoreStatus] = useState<CoreStatus>("unknown");
  const [message, setMessage] = useState<FeedbackMessage | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);

  const coreStatusText = useMemo(() => {
    if (coreStatus === "checking") return "检查中";
    if (coreStatus === "ok") return "核心信号正常";
    if (coreStatus === "failed") return "信号弱";
    return "未检查";
  }, [coreStatus]);

  const coreStatusTone = useMemo(() => {
    if (coreStatus === "ok") return "ok";
    if (coreStatus === "failed") return "failed";
    if (coreStatus === "checking") return "checking";
    return "unknown";
  }, [coreStatus]);

  const refreshAutostart = useCallback(async () => {
    try {
      const enabled = await invoke<boolean>("get_autostart_enabled");
      setAutostartEnabled(enabled);
    } catch {
      setMessage({ tone: "error", text: "读取开机自启状态失败。" });
    }
  }, []);

  const refreshStartupSettings = useCallback(async () => {
    try {
      const nextStartupSettings = await invoke<StartupSettings>("get_startup_settings");
      setStartupSettings(nextStartupSettings);
    } catch {
      setMessage({ tone: "error", text: "读取启动设置失败。" });
    }
  }, []);

  const persistSettings = useCallback(async (nextSettings: DesktopPetSettings) => {
    setSettings(nextSettings);
    writeDesktopPetSettings(nextSettings);
    await emit(SETTINGS_UPDATED_EVENT);
  }, []);

  const toggleAutostart = useCallback(async () => {
    setPendingAction("autostart");
    try {
      const enabled = await invoke<boolean>("set_autostart_enabled", { enabled: !autostartEnabled });
      setAutostartEnabled(enabled);
      setMessage({ tone: "success", text: enabled ? "已开启开机自启。" : "已关闭开机自启。" });
    } catch {
      setMessage({ tone: "error", text: "开机自启切换失败。" });
    } finally {
      setPendingAction(null);
    }
  }, [autostartEnabled]);

  const toggleShowPetOnAutostart = useCallback(async () => {
    setPendingAction("startup");
    const nextStartupSettings = {
      showPetOnAutostart: !startupSettings.showPetOnAutostart
    };
    try {
      const savedStartupSettings = await invoke<StartupSettings>("set_startup_settings", {
        settings: nextStartupSettings
      });
      setStartupSettings(savedStartupSettings);
      setMessage(
        savedStartupSettings.showPetOnAutostart
          ? { tone: "success", text: "开机自启时会显示卡咔。" }
          : { tone: "success", text: "开机自启时只驻留托盘。" }
      );
    } catch {
      setMessage({ tone: "error", text: "启动设置保存失败。" });
    } finally {
      setPendingAction(null);
    }
  }, [startupSettings.showPetOnAutostart]);

  const testCoreConnection = useCallback(async () => {
    setPendingAction("core");
    setCoreStatus("checking");
    setMessage({ tone: "info", text: "正在检查核心信号..." });
    try {
      await invoke("check_kaka_core_health");
      setCoreStatus("ok");
      setMessage({ tone: "success", text: "核心信号正常。" });
    } catch {
      setCoreStatus("failed");
      setMessage({ tone: "error", text: "信号有点弱，核心大脑没连上。" });
    } finally {
      setPendingAction(null);
    }
  }, []);

  const resetWindowPosition = useCallback(async () => {
    setPendingAction("reset");
    try {
      window.localStorage.removeItem(WINDOW_POSITION_STORAGE_KEY);
      await invoke("center_main_window");
      await emit(TRAY_EVENT_RESET_POSITION);
      setMessage({ tone: "success", text: "卡咔回到屏幕中间了。" });
    } catch {
      setMessage({ tone: "error", text: "位置重置失败了。" });
    } finally {
      setPendingAction(null);
    }
  }, []);

  useEffect(() => {
    void refreshAutostart();
    void refreshStartupSettings();
  }, [refreshAutostart, refreshStartupSettings]);

  return (
    <main className="settings-shell">
      <header className="settings-header">
        <div>
          <h1>卡咔设置</h1>
          <p>常驻桌宠控制</p>
        </div>
        <div className={`settings-status-pill ${coreStatusTone}`}>{coreStatusText}</div>
      </header>

      <section className="settings-section">
        <h2>状态</h2>
        <div className="settings-row">
          <span>开机自启</span>
          <strong className={autostartEnabled ? "status-value on" : "status-value off"}>
            {autostartEnabled ? "已开启" : "未开启"}
          </strong>
        </div>
        <div className="settings-row">
          <span>自启显示卡咔</span>
          <strong className={startupSettings.showPetOnAutostart ? "status-value on" : "status-value neutral"}>
            {startupSettings.showPetOnAutostart ? "显示" : "只驻留托盘"}
          </strong>
        </div>
        <div className="settings-row">
          <span>核心连接</span>
          <strong className={`status-value ${coreStatusTone}`}>{coreStatusText}</strong>
        </div>
      </section>

      <section className="settings-section">
        <h2>常用操作</h2>
        <div className="settings-actions">
          <button type="button" disabled={pendingAction !== null} onClick={() => void toggleAutostart()}>
            {pendingAction === "autostart" ? "处理中..." : autostartEnabled ? "关闭开机自启" : "开启开机自启"}
          </button>
          <button type="button" disabled={pendingAction !== null} onClick={() => void testCoreConnection()}>
            {pendingAction === "core" ? "检查中..." : "连接测试"}
          </button>
          <button type="button" disabled={pendingAction !== null} onClick={() => void resetWindowPosition()}>
            {pendingAction === "reset" ? "重置中..." : "重置位置"}
          </button>
        </div>
      </section>

      <section className="settings-section">
        <h2>行为</h2>
        <label className="settings-toggle">
          <input
            type="checkbox"
            checked={startupSettings.showPetOnAutostart}
            disabled={pendingAction !== null}
            onChange={() => void toggleShowPetOnAutostart()}
          />
          <span>开机自启时显示卡咔</span>
        </label>

        <label className="settings-toggle">
          <input
            type="checkbox"
            checked={settings.idleAmbientEnabled}
            disabled={pendingAction !== null}
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
            disabled={pendingAction !== null}
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

      {message && <div className={`settings-message ${message.tone}`}>{message.text}</div>}
    </main>
  );
}
