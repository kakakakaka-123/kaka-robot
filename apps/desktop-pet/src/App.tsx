import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { cursorPosition, getCurrentWindow, PhysicalPosition } from "@tauri-apps/api/window";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  readDesktopPetSettings,
  SETTINGS_UPDATED_EVENT,
  TRAY_EVENT_CHECK_CORE,
  TRAY_EVENT_RESET_POSITION,
  WINDOW_POSITION_STORAGE_KEY
} from "./desktopPetSettings";
import { PetCanvas } from "./PetCanvas";
import { PET_STATE_OPTIONS, PET_STATES, type PetStateId } from "./petStates";

type ContextMenuState = {
  visible: boolean;
  x: number;
  y: number;
};

type SpeechBubbleState = {
  visible: boolean;
  text: string;
};

type StoredWindowPosition = {
  x: number;
  y: number;
};

type PointerSession = {
  pointerId: number;
  startX: number;
  startY: number;
  dragging: boolean;
  windowMoveInFlight: boolean;
  pendingWindowMove: boolean;
  dragOrigin?: {
    cursorX: number;
    cursorY: number;
    windowX: number;
    windowY: number;
  };
};

type PetTouchReaction = {
  stateId: Extract<PetStateId, "pet" | "happy" | "thinking">;
  text: string;
  durationMs: number;
};

const CONTEXT_MENU_WIDTH = 164;
const CONTEXT_MENU_HEIGHT = 151;
const DEBUG_CONTEXT_MENU_HEIGHT = 322;
const CONTEXT_MENU_MARGIN = 8;
const SPEECH_BUBBLE_DURATION_MS = 2600;
const POINTER_DRAG_THRESHOLD_PX = 6;
const IDLE_AMBIENT_MIN_DELAY_MS = 45 * 1000;
const IDLE_AMBIENT_MAX_DELAY_MS = 120 * 1000;

const initialContextMenu: ContextMenuState = {
  visible: false,
  x: 0,
  y: 0
};

const initialSpeechBubble: SpeechBubbleState = {
  visible: false,
  text: ""
};

const PET_STATE_BUBBLE_TEXT: Partial<Record<PetStateId, string>> = {
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

const IDLE_AMBIENT_BUBBLES = [
  "我还在这里。",
  "桌面风平浪静。",
  "卡咔巡视中。",
  "今天也要好好运行。",
  "有事可以摸摸我。",
  "我在旁边待机。"
] as const;

const PET_TOUCH_REACTIONS: readonly PetTouchReaction[] = [
  { stateId: "pet", text: "嘿嘿，再摸一下。", durationMs: 2100 },
  { stateId: "happy", text: "收到摸头，心情加一格。", durationMs: 2400 },
  { stateId: "pet", text: "尾巴要藏好。", durationMs: 2200 },
  { stateId: "thinking", text: "摸头会提高缓存命中率吗...", durationMs: 2600 },
  { stateId: "happy", text: "今天允许你多摸两下。", durationMs: 2400 }
] as const;

const WAKE_BUBBLES = ["唔...我醒啦。", "刚才睡得很轻。", "卡咔重新上线。"] as const;
const DRAG_END_BUBBLES = ["放好啦。", "这个位置也不错。", "卡咔已停稳。"] as const;

const IDLE_AMBIENT_ACTIONS: Array<{
  stateId: Extract<PetStateId, "happy" | "thinking" | "sleepy">;
  durationMs: number;
}> = [
  { stateId: "happy", durationMs: 3200 },
  { stateId: "thinking", durationMs: 4200 },
  { stateId: "sleepy", durationMs: 5200 }
];

function readStoredWindowPosition(): StoredWindowPosition | null {
  try {
    const rawValue = window.localStorage.getItem(WINDOW_POSITION_STORAGE_KEY);
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

function isValidWindowCoordinate(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && Math.abs(value) < 100000;
}

function getRandomInt(min: number, max: number): number {
  return Math.floor(window.crypto.getRandomValues(new Uint32Array(1))[0] / (0xffffffff + 1) * (max - min + 1)) + min;
}

function pickRandomItem<T>(items: readonly T[]): T {
  return items[getRandomInt(0, items.length - 1)];
}

export function App() {
  const [petStateId, setPetStateId] = useState<PetStateId>("idle");
  const [contextMenu, setContextMenu] = useState(initialContextMenu);
  const [speechBubble, setSpeechBubble] = useState(initialSpeechBubble);
  const [settings, setSettings] = useState(() => readDesktopPetSettings());
  const petStateIdRef = useRef<PetStateId>("idle");
  const stateBeforeDragRef = useRef<PetStateId>("idle");
  const pointerSessionRef = useRef<PointerSession | null>(null);
  const petReactionTimerRef = useRef<number | null>(null);
  const speechBubbleTimerRef = useRef<number | null>(null);
  const idleTimerRef = useRef<number | null>(null);
  const idleAmbientTimerRef = useRef<number | null>(null);
  const idleAmbientRestoreTimerRef = useRef<number | null>(null);
  const idleAmbientStateRef = useRef<PetStateId | null>(null);
  const settingsRef = useRef(settings);

  const setPetState = useCallback((nextStateId: PetStateId) => {
    petStateIdRef.current = nextStateId;
    setPetStateId(nextStateId);
  }, []);

  const clearPetReactionTimer = useCallback(() => {
    if (petReactionTimerRef.current === null) return;
    window.clearTimeout(petReactionTimerRef.current);
    petReactionTimerRef.current = null;
  }, []);

  const clearSpeechBubbleTimer = useCallback(() => {
    if (speechBubbleTimerRef.current === null) return;
    window.clearTimeout(speechBubbleTimerRef.current);
    speechBubbleTimerRef.current = null;
  }, []);

  const clearIdleTimer = useCallback(() => {
    if (idleTimerRef.current === null) return;
    window.clearTimeout(idleTimerRef.current);
    idleTimerRef.current = null;
  }, []);

  const clearIdleAmbientTimer = useCallback(() => {
    if (idleAmbientTimerRef.current === null) return;
    window.clearTimeout(idleAmbientTimerRef.current);
    idleAmbientTimerRef.current = null;
  }, []);

  const clearIdleAmbientRestoreTimer = useCallback(() => {
    if (idleAmbientRestoreTimerRef.current === null) return;
    window.clearTimeout(idleAmbientRestoreTimerRef.current);
    idleAmbientRestoreTimerRef.current = null;
  }, []);

  const hideContextMenu = useCallback(() => {
    setContextMenu(initialContextMenu);
  }, []);

  const hideSpeechBubble = useCallback(() => {
    clearSpeechBubbleTimer();
    setSpeechBubble(initialSpeechBubble);
  }, [clearSpeechBubbleTimer]);

  const showSpeechBubble = useCallback(
    (text: string, durationMs = SPEECH_BUBBLE_DURATION_MS) => {
      clearSpeechBubbleTimer();
      setSpeechBubble({ visible: true, text });
      speechBubbleTimerRef.current = window.setTimeout(() => {
        setSpeechBubble(initialSpeechBubble);
        speechBubbleTimerRef.current = null;
      }, durationMs);
    },
    [clearSpeechBubbleTimer]
  );

  const cancelIdleAmbientAction = useCallback(() => {
    clearIdleAmbientRestoreTimer();
    if (idleAmbientStateRef.current && petStateIdRef.current === idleAmbientStateRef.current) {
      setPetState("idle");
    }
    idleAmbientStateRef.current = null;
  }, [clearIdleAmbientRestoreTimer, setPetState]);

  const scheduleIdleAmbient = useCallback(() => {
    clearIdleAmbientTimer();
    if (!settingsRef.current.idleAmbientEnabled) return;

    const nextDelayMs = getRandomInt(IDLE_AMBIENT_MIN_DELAY_MS, IDLE_AMBIENT_MAX_DELAY_MS);

    idleAmbientTimerRef.current = window.setTimeout(() => {
      idleAmbientTimerRef.current = null;

      if (petStateIdRef.current !== "idle" || contextMenu.visible || pointerSessionRef.current?.dragging) {
        scheduleIdleAmbient();
        return;
      }

      if (getRandomInt(0, 1) === 0) {
        showSpeechBubble(pickRandomItem(IDLE_AMBIENT_BUBBLES));
      } else {
        const action = pickRandomItem(IDLE_AMBIENT_ACTIONS);
        idleAmbientStateRef.current = action.stateId;
        setPetState(action.stateId);
        const bubbleText = PET_STATE_BUBBLE_TEXT[action.stateId];
        if (bubbleText) {
          showSpeechBubble(bubbleText);
        }

        clearIdleAmbientRestoreTimer();
        idleAmbientRestoreTimerRef.current = window.setTimeout(() => {
          if (idleAmbientStateRef.current === action.stateId && petStateIdRef.current === action.stateId) {
            setPetState("idle");
          }
          idleAmbientStateRef.current = null;
          idleAmbientRestoreTimerRef.current = null;
        }, action.durationMs);
      }

      scheduleIdleAmbient();
    }, nextDelayMs);
  }, [
    clearIdleAmbientRestoreTimer,
    clearIdleAmbientTimer,
    contextMenu.visible,
    setPetState,
    showSpeechBubble
  ]);

  const resetIdleTimer = useCallback(() => {
    clearIdleTimer();
    const idleSleepDelayMs = settingsRef.current.idleSleepDelayMs;
    if (idleSleepDelayMs === null) return;

    idleTimerRef.current = window.setTimeout(() => {
      clearPetReactionTimer();
      if (petStateIdRef.current !== "drag") {
        showSpeechBubble(PET_STATE_BUBBLE_TEXT.sleep ?? "我先睡一会儿...");
        setPetState("sleep");
      }
    }, idleSleepDelayMs);
  }, [clearIdleTimer, clearPetReactionTimer, setPetState, showSpeechBubble]);

  const registerActivity = useCallback(() => {
    cancelIdleAmbientAction();
    const wasSleeping = petStateIdRef.current === "sleep";
    resetIdleTimer();
    if (wasSleeping) {
      setPetState("idle");
      showSpeechBubble(pickRandomItem(WAKE_BUBBLES));
    }
  }, [cancelIdleAmbientAction, resetIdleTimer, setPetState, showSpeechBubble]);

  const saveWindowPosition = useCallback(async () => {
    try {
      const position = await getCurrentWindow().outerPosition();
      window.localStorage.setItem(
        WINDOW_POSITION_STORAGE_KEY,
        JSON.stringify({
          x: Math.round(position.x),
          y: Math.round(position.y)
        })
      );
    } catch {
      // 浏览器预览环境没有 Tauri 窗口对象，忽略即可。
    }
  }, []);

  const restoreStateAfterDrag = useCallback(() => {
    if (petStateIdRef.current === "drag") {
      setPetState(stateBeforeDragRef.current);
    }
  }, [setPetState]);

  const moveWindowToCursor = useCallback(async () => {
    const pointerSession = pointerSessionRef.current;
    if (!pointerSession || !pointerSession.dragging || !pointerSession.dragOrigin) return;

    if (pointerSession.windowMoveInFlight) {
      pointerSession.pendingWindowMove = true;
      return;
    }

    pointerSession.windowMoveInFlight = true;
    try {
      do {
        pointerSession.pendingWindowMove = false;
        const latestSession = pointerSessionRef.current;
        if (!latestSession || !latestSession.dragging || !latestSession.dragOrigin) return;

        const cursor = await cursorPosition();
        const activeSession = pointerSessionRef.current;
        if (!activeSession || !activeSession.dragging || !activeSession.dragOrigin) return;

        const nextX = activeSession.dragOrigin.windowX + cursor.x - activeSession.dragOrigin.cursorX;
        const nextY = activeSession.dragOrigin.windowY + cursor.y - activeSession.dragOrigin.cursorY;
        await getCurrentWindow().setPosition(new PhysicalPosition(Math.round(nextX), Math.round(nextY)));
      } while (pointerSessionRef.current?.pendingWindowMove);
    } catch {
      // 浏览器预览环境没有 Tauri 窗口对象，忽略即可。
    } finally {
      const activeSession = pointerSessionRef.current;
      if (activeSession) {
        activeSession.windowMoveInFlight = false;
      }
    }
  }, []);

  const startWindowDrag = useCallback(async () => {
    hideContextMenu();
    registerActivity();
    clearPetReactionTimer();
    hideSpeechBubble();
    stateBeforeDragRef.current =
      petStateIdRef.current === "drag" || petStateIdRef.current === "pet" || petStateIdRef.current === "sleep"
        ? "idle"
        : petStateIdRef.current;
    setPetState("drag");
    try {
      const [windowPosition, cursor] = await Promise.all([getCurrentWindow().outerPosition(), cursorPosition()]);
      const pointerSession = pointerSessionRef.current;
      if (!pointerSession || !pointerSession.dragging) return;

      pointerSession.dragOrigin = {
        cursorX: cursor.x,
        cursorY: cursor.y,
        windowX: windowPosition.x,
        windowY: windowPosition.y
      };
      void moveWindowToCursor();
    } catch {
      // 浏览器预览环境没有 Tauri 窗口对象，忽略即可。
    }
  }, [clearPetReactionTimer, hideContextMenu, hideSpeechBubble, moveWindowToCursor, registerActivity, setPetState]);

  const triggerPetReaction = useCallback(() => {
    hideContextMenu();
    registerActivity();
    clearPetReactionTimer();
    const reaction = pickRandomItem(PET_TOUCH_REACTIONS);
    setPetState(reaction.stateId);
    showSpeechBubble(reaction.text);
    petReactionTimerRef.current = window.setTimeout(() => {
      if (petStateIdRef.current === reaction.stateId) {
        setPetState("idle");
      }
      petReactionTimerRef.current = null;
    }, reaction.durationMs);
  }, [clearPetReactionTimer, hideContextMenu, registerActivity, setPetState, showSpeechBubble]);

  const beginPetPointer = useCallback(
    (event: React.PointerEvent<HTMLButtonElement>) => {
      if (event.button !== 0) return;

      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      pointerSessionRef.current = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        dragging: false,
        windowMoveInFlight: false,
        pendingWindowMove: false
      };
      hideContextMenu();
      registerActivity();
    },
    [hideContextMenu, registerActivity]
  );

  const movePetPointer = useCallback(
    (event: React.PointerEvent<HTMLButtonElement>) => {
      const pointerSession = pointerSessionRef.current;
      if (!pointerSession || pointerSession.pointerId !== event.pointerId) return;

      if (pointerSession.dragging) {
        void moveWindowToCursor();
        return;
      }

      const deltaX = event.clientX - pointerSession.startX;
      const deltaY = event.clientY - pointerSession.startY;
      if (Math.hypot(deltaX, deltaY) < POINTER_DRAG_THRESHOLD_PX) return;

      pointerSession.dragging = true;
      void startWindowDrag();
    },
    [moveWindowToCursor, startWindowDrag]
  );

  const endPetPointer = useCallback(
    (event: React.PointerEvent<HTMLButtonElement>) => {
      const pointerSession = pointerSessionRef.current;
      if (!pointerSession || pointerSession.pointerId !== event.pointerId) return;

      pointerSessionRef.current = null;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }

      if (pointerSession.dragging) {
        restoreStateAfterDrag();
        showSpeechBubble(pickRandomItem(DRAG_END_BUBBLES), 1800);
        window.setTimeout(() => void saveWindowPosition(), 80);
      } else {
        triggerPetReaction();
      }
    },
    [restoreStateAfterDrag, saveWindowPosition, showSpeechBubble, triggerPetReaction]
  );

  const cancelPetPointer = useCallback(
    (event: React.PointerEvent<HTMLButtonElement>) => {
      const pointerSession = pointerSessionRef.current;
      if (!pointerSession || pointerSession.pointerId !== event.pointerId) return;

      pointerSessionRef.current = null;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      if (pointerSession.dragging) {
        restoreStateAfterDrag();
        window.setTimeout(() => void saveWindowPosition(), 80);
      }
    },
    [restoreStateAfterDrag, saveWindowPosition]
  );

  const showContextMenu = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    registerActivity();
    const menuHeight = settingsRef.current.debugStateMenuEnabled ? DEBUG_CONTEXT_MENU_HEIGHT : CONTEXT_MENU_HEIGHT;
    const maxX = window.innerWidth - CONTEXT_MENU_WIDTH - CONTEXT_MENU_MARGIN;
    const maxY = window.innerHeight - menuHeight - CONTEXT_MENU_MARGIN;
    setContextMenu({
      visible: true,
      x: Math.max(CONTEXT_MENU_MARGIN, Math.min(event.clientX, maxX)),
      y: Math.max(CONTEXT_MENU_MARGIN, Math.min(event.clientY, maxY))
    });
  }, [registerActivity]);

  const selectPetState = useCallback(
    (stateId: PetStateId) => {
      registerActivity();
      clearIdleAmbientRestoreTimer();
      idleAmbientStateRef.current = null;
      clearPetReactionTimer();
      setPetState(stateId);
      const bubbleText = PET_STATE_BUBBLE_TEXT[stateId];
      if (bubbleText) {
        showSpeechBubble(bubbleText);
      }
      hideContextMenu();
    },
    [clearIdleAmbientRestoreTimer, clearPetReactionTimer, hideContextMenu, registerActivity, setPetState, showSpeechBubble]
  );

  const openSettings = useCallback(async () => {
    registerActivity();
    hideContextMenu();
    try {
      await invoke("show_settings_window");
    } catch {
      showSpeechBubble("设置窗口暂时打不开。");
    }
  }, [hideContextMenu, registerActivity, showSpeechBubble]);

  const hideMainWindow = useCallback(async () => {
    registerActivity();
    hideContextMenu();
    try {
      await invoke("set_main_window_visible", { visible: false });
    } catch {
      showSpeechBubble("隐藏失败了。");
    }
  }, [hideContextMenu, registerActivity, showSpeechBubble]);

  const testCoreConnection = useCallback(async () => {
    registerActivity();
    clearPetReactionTimer();
    hideContextMenu();
    setPetState("loading");
    showSpeechBubble("正在检查核心信号...");

    try {
      await invoke("check_kaka_core_health");
      setPetState("message");
      showSpeechBubble("核心信号正常。");
    } catch {
      setPetState("weakSignal");
      showSpeechBubble("信号有点弱，核心大脑没连上。");
    }
  }, [clearPetReactionTimer, hideContextMenu, registerActivity, setPetState, showSpeechBubble]);

  const resetWindowPosition = useCallback(async () => {
    registerActivity();
    hideContextMenu();
    window.localStorage.removeItem(WINDOW_POSITION_STORAGE_KEY);

    try {
      await getCurrentWindow().center();
      setPetState("idle");
      showSpeechBubble("卡咔回到屏幕中间了。");
    } catch {
      showSpeechBubble("位置重置失败了。");
    }
  }, [hideContextMenu, registerActivity, setPetState, showSpeechBubble]);

  const quit = useCallback(async () => {
    try {
      await invoke("quit_app");
    } catch {
      window.close();
    }
  }, []);

  useEffect(() => {
    const storedPosition = readStoredWindowPosition();
    if (storedPosition) {
      void getCurrentWindow().setPosition(new PhysicalPosition(storedPosition.x, storedPosition.y));
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    const unlisteners: UnlistenFn[] = [];

    const addTrayListener = async (eventName: string, handler: () => void | Promise<void>) => {
      try {
        const unlisten = await listen(eventName, () => {
          void handler();
        });
        if (disposed) {
          unlisten();
        } else {
          unlisteners.push(unlisten);
        }
      } catch {
        // 浏览器预览环境没有 Tauri 事件通道，忽略即可。
      }
    };

    void addTrayListener(TRAY_EVENT_RESET_POSITION, resetWindowPosition);
    void addTrayListener(TRAY_EVENT_CHECK_CORE, testCoreConnection);

    return () => {
      disposed = true;
      for (const unlisten of unlisteners) {
        unlisten();
      }
    };
  }, [resetWindowPosition, testCoreConnection]);

  useEffect(() => {
    const applySettings = () => {
      const nextSettings = readDesktopPetSettings();
      settingsRef.current = nextSettings;
      setSettings(nextSettings);
      if (!settingsRef.current.idleAmbientEnabled) {
        cancelIdleAmbientAction();
        clearIdleAmbientTimer();
      } else {
        scheduleIdleAmbient();
      }
      resetIdleTimer();
    };

    let disposed = false;
    let unlistenSettings: UnlistenFn | null = null;
    void listen(SETTINGS_UPDATED_EVENT, applySettings)
      .then((unlisten) => {
        if (disposed) {
          unlisten();
        } else {
          unlistenSettings = unlisten;
        }
      })
      .catch(() => {
        // 浏览器预览环境没有 Tauri 事件通道，忽略即可。
      });

    window.addEventListener("storage", applySettings);
    return () => {
      disposed = true;
      window.removeEventListener("storage", applySettings);
      unlistenSettings?.();
    };
  }, [cancelIdleAmbientAction, clearIdleAmbientTimer, resetIdleTimer, scheduleIdleAmbient]);

  useEffect(() => {
    resetIdleTimer();
    scheduleIdleAmbient();
    return () => {
      clearIdleTimer();
      clearIdleAmbientTimer();
      clearIdleAmbientRestoreTimer();
      idleAmbientStateRef.current = null;
      clearPetReactionTimer();
      clearSpeechBubbleTimer();
    };
  }, [
    clearIdleAmbientRestoreTimer,
    clearIdleAmbientTimer,
    clearIdleTimer,
    clearPetReactionTimer,
    clearSpeechBubbleTimer,
    resetIdleTimer,
    scheduleIdleAmbient
  ]);

  useEffect(() => {
    const onPointerDown = () => {
      hideContextMenu();
      registerActivity();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      registerActivity();
      if (event.key === "Escape") hideContextMenu();
    };

    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [hideContextMenu, registerActivity]);

  return (
    <main className="pet-shell" onContextMenu={showContextMenu}>
      <div className="state-pill">{PET_STATES[petStateId].label}</div>
      {speechBubble.visible && (
        <div className="speech-bubble" role="status" aria-live="polite">
          {speechBubble.text}
        </div>
      )}
      <button
        type="button"
        className="drag-layer"
        aria-label="拖拽卡咔"
        onPointerDown={beginPetPointer}
        onPointerMove={movePetPointer}
        onPointerUp={endPetPointer}
        onPointerCancel={cancelPetPointer}
      />
      <PetCanvas stateId={petStateId} />
      {contextMenu.visible && (
        <div
          className="context-menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <div className="menu-primary-actions">
            <button
              type="button"
              className="menu-action-button pet-action-button"
              onClick={() => {
                triggerPetReaction();
              }}
            >
              摸摸头
            </button>
            <button
              type="button"
              className="menu-action-button settings-button"
              onClick={() => void openSettings()}
            >
              设置
            </button>
            <button
              type="button"
              className="menu-action-button hide-button"
              onClick={() => void hideMainWindow()}
            >
              隐藏
            </button>
            <button type="button" className="menu-action-button quit-button" onClick={() => void quit()}>
              退出
            </button>
          </div>
          {settings.debugStateMenuEnabled && (
            <div className="debug-menu-section">
              <div className="context-menu-title">调试</div>
              <div className="menu-actions">
                <button
                  type="button"
                  className="menu-action-button connection-button"
                  onClick={() => void testCoreConnection()}
                >
                  连接测试
                </button>
                <button
                  type="button"
                  className="menu-action-button reset-position-button"
                  onClick={() => void resetWindowPosition()}
                >
                  重置位置
                </button>
              </div>
              <div className="context-menu-title">切换状态</div>
              <div className="state-menu">
                {PET_STATE_OPTIONS.map((state) => (
                  <button
                    key={state.id}
                    type="button"
                    className={state.id === petStateId ? "active" : ""}
                    onClick={() => {
                      selectPetState(state.id);
                    }}
                  >
                    {state.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
