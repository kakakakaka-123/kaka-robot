import { invoke } from "@tauri-apps/api/core";
import { cursorPosition, getCurrentWindow, PhysicalPosition } from "@tauri-apps/api/window";
import { useCallback, useEffect, useRef, useState } from "react";

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

const CONTEXT_MENU_WIDTH = 164;
const CONTEXT_MENU_HEIGHT = 218;
const CONTEXT_MENU_MARGIN = 8;
const PET_REACTION_DURATION_MS = 2000;
const SPEECH_BUBBLE_DURATION_MS = 2600;
const IDLE_SLEEP_DELAY_MS = 2 * 60 * 1000;
const POINTER_DRAG_THRESHOLD_PX = 6;

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

export function App() {
  const [petStateId, setPetStateId] = useState<PetStateId>("idle");
  const [contextMenu, setContextMenu] = useState(initialContextMenu);
  const [speechBubble, setSpeechBubble] = useState(initialSpeechBubble);
  const petStateIdRef = useRef<PetStateId>("idle");
  const stateBeforeDragRef = useRef<PetStateId>("idle");
  const pointerSessionRef = useRef<PointerSession | null>(null);
  const petReactionTimerRef = useRef<number | null>(null);
  const speechBubbleTimerRef = useRef<number | null>(null);
  const idleTimerRef = useRef<number | null>(null);

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

  const resetIdleTimer = useCallback(() => {
    clearIdleTimer();
    idleTimerRef.current = window.setTimeout(() => {
      clearPetReactionTimer();
      if (petStateIdRef.current !== "drag") {
        showSpeechBubble(PET_STATE_BUBBLE_TEXT.sleep ?? "我先睡一会儿...");
        setPetState("sleep");
      }
    }, IDLE_SLEEP_DELAY_MS);
  }, [clearIdleTimer, clearPetReactionTimer, setPetState, showSpeechBubble]);

  const registerActivity = useCallback(() => {
    const wasSleeping = petStateIdRef.current === "sleep";
    resetIdleTimer();
    if (wasSleeping) {
      setPetState("idle");
      showSpeechBubble("唔...我醒啦。");
    }
  }, [resetIdleTimer, setPetState, showSpeechBubble]);

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
    setPetState("pet");
    showSpeechBubble(PET_STATE_BUBBLE_TEXT.pet ?? "嘿嘿。");
    petReactionTimerRef.current = window.setTimeout(() => {
      if (petStateIdRef.current === "pet") {
        setPetState("idle");
      }
      petReactionTimerRef.current = null;
    }, PET_REACTION_DURATION_MS);
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
      } else {
        triggerPetReaction();
      }
    },
    [restoreStateAfterDrag, triggerPetReaction]
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
      }
    },
    [restoreStateAfterDrag]
  );

  const showContextMenu = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    registerActivity();
    const maxX = window.innerWidth - CONTEXT_MENU_WIDTH - CONTEXT_MENU_MARGIN;
    const maxY = window.innerHeight - CONTEXT_MENU_HEIGHT - CONTEXT_MENU_MARGIN;
    setContextMenu({
      visible: true,
      x: Math.max(CONTEXT_MENU_MARGIN, Math.min(event.clientX, maxX)),
      y: Math.max(CONTEXT_MENU_MARGIN, Math.min(event.clientY, maxY))
    });
  }, [registerActivity]);

  const selectPetState = useCallback(
    (stateId: PetStateId) => {
      registerActivity();
      clearPetReactionTimer();
      setPetState(stateId);
      const bubbleText = PET_STATE_BUBBLE_TEXT[stateId];
      if (bubbleText) {
        showSpeechBubble(bubbleText);
      }
      hideContextMenu();
    },
    [clearPetReactionTimer, hideContextMenu, registerActivity, setPetState, showSpeechBubble]
  );

  const quit = useCallback(async () => {
    try {
      await invoke("quit_app");
    } catch {
      window.close();
    }
  }, []);

  useEffect(() => {
    resetIdleTimer();
    return () => {
      clearIdleTimer();
      clearPetReactionTimer();
      clearSpeechBubbleTimer();
    };
  }, [clearIdleTimer, clearPetReactionTimer, clearSpeechBubbleTimer, resetIdleTimer]);

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
          <button type="button" className="quit-button" onClick={() => void quit()}>
            退出
          </button>
        </div>
      )}
    </main>
  );
}
