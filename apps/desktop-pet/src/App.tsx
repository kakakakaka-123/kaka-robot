import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { cursorPosition, getCurrentWindow, PhysicalPosition } from "@tauri-apps/api/window";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  type DesktopPetSettings,
  readDesktopPetSettings,
  SETTINGS_UPDATED_EVENT,
  TRAY_EVENT_CHECK_CORE,
  TRAY_EVENT_RESET_POSITION,
  WINDOW_POSITION_STORAGE_KEY
} from "./desktopPetSettings";
import { PetCanvas } from "./PetCanvas";
import {
  createPetBehaviorMemory,
  getDoubleTouchReaction,
  getDragEndReaction,
  getIdleAmbientReaction,
  getLongDragReaction,
  getLongPressReaction,
  getSleepReaction,
  getStateBubbleText,
  getTouchReaction,
  getWakeReaction,
  type PetBehaviorReaction
} from "./petBehavior";
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
  longDragNotified: boolean;
  longPressTriggered: boolean;
  windowMoveInFlight: boolean;
  pendingWindowMove: boolean;
  dragStartedAt?: number;
  dragOrigin?: {
    cursorX: number;
    cursorY: number;
    windowX: number;
    windowY: number;
  };
};

const CONTEXT_MENU_WIDTH = 164;
const CONTEXT_MENU_HEIGHT = 151;
const DEBUG_CONTEXT_MENU_HEIGHT = 322;
const CONTEXT_MENU_MARGIN = 8;
const POINTER_DRAG_THRESHOLD_PX = 6;
const DOUBLE_TOUCH_WINDOW_MS = 260;
const LONG_PRESS_DELAY_MS = 720;
const LONG_DRAG_DELAY_MS = 4200;
const IDLE_AMBIENT_DELAY_MS = {
  low: { min: 90 * 1000, max: 180 * 1000 },
  normal: { min: 45 * 1000, max: 120 * 1000 },
  high: { min: 20 * 1000, max: 55 * 1000 }
} as const;

const initialContextMenu: ContextMenuState = {
  visible: false,
  x: 0,
  y: 0
};

const initialSpeechBubble: SpeechBubbleState = {
  visible: false,
  text: ""
};

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

export function App() {
  const [petStateId, setPetStateId] = useState<PetStateId>("idle");
  const [contextMenu, setContextMenu] = useState(initialContextMenu);
  const [speechBubble, setSpeechBubble] = useState(initialSpeechBubble);
  const [settings, setSettings] = useState(() => readDesktopPetSettings());
  const petStateIdRef = useRef<PetStateId>("idle");
  const stateBeforeDragRef = useRef<PetStateId>("idle");
  const behaviorMemoryRef = useRef(createPetBehaviorMemory());
  const pointerSessionRef = useRef<PointerSession | null>(null);
  const petReactionTimerRef = useRef<number | null>(null);
  const speechBubbleTimerRef = useRef<number | null>(null);
  const touchReactionTimerRef = useRef<number | null>(null);
  const longPressTimerRef = useRef<number | null>(null);
  const doubleTouchPointerIdRef = useRef<number | null>(null);
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

  const clearTouchReactionTimer = useCallback(() => {
    if (touchReactionTimerRef.current === null) return;
    window.clearTimeout(touchReactionTimerRef.current);
    touchReactionTimerRef.current = null;
  }, []);

  const clearLongPressTimer = useCallback(() => {
    if (longPressTimerRef.current === null) return;
    window.clearTimeout(longPressTimerRef.current);
    longPressTimerRef.current = null;
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
    (text: string, durationMs: number = settingsRef.current.speechBubbleDurationMs) => {
      clearSpeechBubbleTimer();
      setSpeechBubble({ visible: true, text });
      speechBubbleTimerRef.current = window.setTimeout(() => {
        setSpeechBubble(initialSpeechBubble);
        speechBubbleTimerRef.current = null;
      }, durationMs);
    },
    [clearSpeechBubbleTimer]
  );

  const playPetReaction = useCallback(
    (reaction: PetBehaviorReaction, restoreState = true) => {
      clearPetReactionTimer();
      if (reaction.stateId) {
        setPetState(reaction.stateId);
      }
      showSpeechBubble(reaction.text, reaction.durationMs);

      if (!restoreState || !reaction.stateId) return;

      petReactionTimerRef.current = window.setTimeout(() => {
        if (reaction.stateId && petStateIdRef.current === reaction.stateId) {
          setPetState("idle");
        }
        petReactionTimerRef.current = null;
      }, reaction.durationMs);
    },
    [clearPetReactionTimer, setPetState, showSpeechBubble]
  );

  const applyWindowSettings = useCallback((nextSettings: DesktopPetSettings) => {
    void invoke("set_main_window_size", { size: nextSettings.petWindowSizePx });
    void invoke("set_main_window_always_on_top", { enabled: nextSettings.alwaysOnTopEnabled });
  }, []);

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

    const delayRange = IDLE_AMBIENT_DELAY_MS[settingsRef.current.idleAmbientFrequency];
    const nextDelayMs = getRandomInt(delayRange.min, delayRange.max);

    idleAmbientTimerRef.current = window.setTimeout(() => {
      idleAmbientTimerRef.current = null;

      if (petStateIdRef.current !== "idle" || contextMenu.visible || pointerSessionRef.current?.dragging) {
        scheduleIdleAmbient();
        return;
      }

      const reaction = getIdleAmbientReaction(behaviorMemoryRef.current);
      if (reaction.stateId) {
        idleAmbientStateRef.current = reaction.stateId;
        setPetState(reaction.stateId);
        showSpeechBubble(reaction.text, reaction.durationMs);
        clearIdleAmbientRestoreTimer();
        idleAmbientRestoreTimerRef.current = window.setTimeout(() => {
          if (idleAmbientStateRef.current === reaction.stateId && petStateIdRef.current === reaction.stateId) {
            setPetState("idle");
          }
          idleAmbientStateRef.current = null;
          idleAmbientRestoreTimerRef.current = null;
        }, reaction.durationMs);
      } else {
        showSpeechBubble(reaction.text, reaction.durationMs);
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
      idleTimerRef.current = null;
      clearPetReactionTimer();
      if (petStateIdRef.current !== "drag") {
        const reaction = getSleepReaction(behaviorMemoryRef.current);
        if (!reaction) {
          return;
        }
        setPetState(reaction.stateId ?? "sleep");
        showSpeechBubble(reaction.text, reaction.durationMs);
      }
    }, idleSleepDelayMs);
  }, [clearIdleTimer, clearPetReactionTimer, setPetState, showSpeechBubble]);

  const registerActivity = useCallback(() => {
    cancelIdleAmbientAction();
    const wasSleeping = petStateIdRef.current === "sleep";
    resetIdleTimer();
    if (wasSleeping) {
      setPetState("idle");
      const reaction = getWakeReaction(behaviorMemoryRef.current);
      showSpeechBubble(reaction.text, reaction.durationMs);
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
    clearLongPressTimer();
    clearTouchReactionTimer();
    playPetReaction(getTouchReaction(behaviorMemoryRef.current));
  }, [clearLongPressTimer, clearTouchReactionTimer, hideContextMenu, playPetReaction, registerActivity]);

  const queueTouchReaction = useCallback(() => {
    clearLongPressTimer();
    touchReactionTimerRef.current = window.setTimeout(() => {
      touchReactionTimerRef.current = null;
      playPetReaction(getTouchReaction(behaviorMemoryRef.current));
    }, DOUBLE_TOUCH_WINDOW_MS);
  }, [clearLongPressTimer, playPetReaction]);

  const triggerDoubleTouchReaction = useCallback(() => {
    clearLongPressTimer();
    clearTouchReactionTimer();
    doubleTouchPointerIdRef.current = null;
    playPetReaction(getDoubleTouchReaction(behaviorMemoryRef.current));
  }, [clearLongPressTimer, clearTouchReactionTimer, playPetReaction]);

  const triggerLongPressReaction = useCallback(
    (pointerId: number) => {
      const pointerSession = pointerSessionRef.current;
      if (!pointerSession || pointerSession.pointerId !== pointerId || pointerSession.dragging) return;

      pointerSession.longPressTriggered = true;
      doubleTouchPointerIdRef.current = null;
      clearTouchReactionTimer();
      playPetReaction(getLongPressReaction(behaviorMemoryRef.current));
    },
    [clearTouchReactionTimer, playPetReaction]
  );

  const maybeTriggerLongDragReaction = useCallback(() => {
    const pointerSession = pointerSessionRef.current;
    if (!pointerSession?.dragging || pointerSession.longDragNotified || pointerSession.dragStartedAt === undefined) {
      return;
    }

    if (window.performance.now() - pointerSession.dragStartedAt < LONG_DRAG_DELAY_MS) return;

    pointerSession.longDragNotified = true;
    playPetReaction(getLongDragReaction(behaviorMemoryRef.current), false);
  }, [playPetReaction]);

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
        longDragNotified: false,
        longPressTriggered: false,
        windowMoveInFlight: false,
        pendingWindowMove: false
      };
      if (touchReactionTimerRef.current !== null) {
        clearTouchReactionTimer();
        doubleTouchPointerIdRef.current = event.pointerId;
      } else {
        doubleTouchPointerIdRef.current = null;
      }
      clearLongPressTimer();
      longPressTimerRef.current = window.setTimeout(() => {
        longPressTimerRef.current = null;
        triggerLongPressReaction(event.pointerId);
      }, LONG_PRESS_DELAY_MS);
      hideContextMenu();
      registerActivity();
    },
    [clearLongPressTimer, clearTouchReactionTimer, hideContextMenu, registerActivity, triggerLongPressReaction]
  );

  const movePetPointer = useCallback(
    (event: React.PointerEvent<HTMLButtonElement>) => {
      const pointerSession = pointerSessionRef.current;
      if (!pointerSession || pointerSession.pointerId !== event.pointerId) return;

      if (pointerSession.dragging) {
        maybeTriggerLongDragReaction();
        void moveWindowToCursor();
        return;
      }

      const deltaX = event.clientX - pointerSession.startX;
      const deltaY = event.clientY - pointerSession.startY;
      if (Math.hypot(deltaX, deltaY) < POINTER_DRAG_THRESHOLD_PX) return;

      pointerSession.dragging = true;
      pointerSession.dragStartedAt = window.performance.now();
      doubleTouchPointerIdRef.current = null;
      clearLongPressTimer();
      void startWindowDrag();
    },
    [clearLongPressTimer, maybeTriggerLongDragReaction, moveWindowToCursor, startWindowDrag]
  );

  const endPetPointer = useCallback(
    (event: React.PointerEvent<HTMLButtonElement>) => {
      const pointerSession = pointerSessionRef.current;
      if (!pointerSession || pointerSession.pointerId !== event.pointerId) return;

      pointerSessionRef.current = null;
      clearLongPressTimer();
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }

      if (pointerSession.dragging) {
        doubleTouchPointerIdRef.current = null;
        restoreStateAfterDrag();
        const reaction = getDragEndReaction(behaviorMemoryRef.current);
        showSpeechBubble(reaction.text, reaction.durationMs);
        window.setTimeout(() => void saveWindowPosition(), 80);
      } else if (pointerSession.longPressTriggered) {
        doubleTouchPointerIdRef.current = null;
      } else if (doubleTouchPointerIdRef.current === event.pointerId) {
        triggerDoubleTouchReaction();
      } else {
        queueTouchReaction();
      }
    },
    [
      clearLongPressTimer,
      queueTouchReaction,
      restoreStateAfterDrag,
      saveWindowPosition,
      showSpeechBubble,
      triggerDoubleTouchReaction
    ]
  );

  const cancelPetPointer = useCallback(
    (event: React.PointerEvent<HTMLButtonElement>) => {
      const pointerSession = pointerSessionRef.current;
      if (!pointerSession || pointerSession.pointerId !== event.pointerId) return;

      pointerSessionRef.current = null;
      doubleTouchPointerIdRef.current = null;
      clearLongPressTimer();
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      if (pointerSession.dragging) {
        restoreStateAfterDrag();
        window.setTimeout(() => void saveWindowPosition(), 80);
      }
    },
    [clearLongPressTimer, restoreStateAfterDrag, saveWindowPosition]
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
      const bubbleText = getStateBubbleText(stateId);
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
    applyWindowSettings(settingsRef.current);
  }, [applyWindowSettings]);

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
      applyWindowSettings(nextSettings);
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
  }, [applyWindowSettings, cancelIdleAmbientAction, clearIdleAmbientTimer, resetIdleTimer, scheduleIdleAmbient]);

  useEffect(() => {
    resetIdleTimer();
    scheduleIdleAmbient();
    return () => {
      clearIdleTimer();
      clearIdleAmbientTimer();
      clearIdleAmbientRestoreTimer();
      idleAmbientStateRef.current = null;
      clearPetReactionTimer();
      clearTouchReactionTimer();
      clearLongPressTimer();
      clearSpeechBubbleTimer();
    };
  }, [
    clearIdleAmbientRestoreTimer,
    clearIdleAmbientTimer,
    clearIdleTimer,
    clearLongPressTimer,
    clearPetReactionTimer,
    clearSpeechBubbleTimer,
    clearTouchReactionTimer,
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
      {settings.showStateLabel && <div className="state-pill">{PET_STATES[petStateId].label}</div>}
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
