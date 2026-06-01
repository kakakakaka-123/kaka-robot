import { Application, Sprite, Texture } from "pixi.js";
import { useEffect, useRef } from "react";

import { createPetTextureCache, loadPetTexture, preloadInitialPetTextures, type PetTextureCache } from "./petTextureCache";
import { PET_STATES, type PetStateId } from "./petStates";

const PET_DISPLAY_HEIGHT_RATIO = 220 / 280;
const BASELINE_OFFSET = 8;

type PetCanvasProps = {
  stateId: PetStateId;
};

type MountedPet = {
  app: Application;
  pet: Sprite;
  textureCache: PetTextureCache;
};

type MotionFrame = {
  x: number;
  y: number;
  rotation: number;
  scaleX: number;
  scaleY: number;
  alpha: number;
};

export function PetCanvas({ stateId }: PetCanvasProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mountedPetRef = useRef<MountedPet | null>(null);
  const stateIdRef = useRef(stateId);
  const stateChangedAtRef = useRef(0);

  useEffect(() => {
    const previousStateId = stateIdRef.current;
    stateIdRef.current = stateId;
    const mountedPet = mountedPetRef.current;
    if (mountedPet) {
      if (previousStateId !== stateId) {
        stateChangedAtRef.current = window.performance.now();
      }
      void loadPetTexture(mountedPet.textureCache, stateId).then((texture) => {
        if (stateIdRef.current === stateId) {
          mountedPet.pet.texture = texture;
        }
      });
    }
  }, [stateId]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let pixiApp: Application | null = null;
    let destroyed = false;

    async function mount(hostElement: HTMLElement) {
      const app = new Application();
      await app.init({
        backgroundAlpha: 0,
        antialias: true,
        autoDensity: true,
        resizeTo: hostElement,
        resolution: Math.max(1, window.devicePixelRatio || 1)
      });

      if (destroyed) {
        app.destroy(true);
        return;
      }

      pixiApp = app;
      app.canvas.className = "pet-canvas";
      hostElement.appendChild(app.canvas);

      const textureCache = createPetTextureCache();
      const initialTexture = await loadPetTexture(textureCache, stateIdRef.current);
      if (destroyed) return;

      const pet = new Sprite(initialTexture);
      pet.anchor.set(0.5, 1);
      pet.scale.set(getPetBaseScale(app, pet));
      pet.x = app.renderer.width / 2;
      pet.y = app.renderer.height - BASELINE_OFFSET;
      app.stage.addChild(pet);
      mountedPetRef.current = { app, pet, textureCache };
      stateChangedAtRef.current = window.performance.now();
      preloadInitialPetTextures(textureCache, stateIdRef.current);

      app.ticker.add(() => {
        const elapsed = window.performance.now();
        const state = PET_STATES[stateIdRef.current];
        const motion = getMotionFrame(state.id, state.motion, elapsed);
        const transition = getStateTransitionFrame(elapsed - stateChangedAtRef.current);
        const baseScale = getPetBaseScale(app, pet);
        pet.x = app.renderer.width / 2 + motion.x;
        pet.y = app.renderer.height - BASELINE_OFFSET + motion.y + transition.y;
        pet.rotation = motion.rotation + transition.rotation;
        pet.alpha = motion.alpha * transition.alpha;
        pet.scale.set(baseScale * motion.scaleX * transition.scaleX, baseScale * motion.scaleY * transition.scaleY);
      });
    }

    void mount(host);

    return () => {
      destroyed = true;
      mountedPetRef.current = null;
      pixiApp?.destroy(true, { children: true, texture: false });
      pixiApp = null;
    };
  }, []);

  return <div ref={hostRef} className="pet-stage" aria-hidden="true" />;
}

function getPetBaseScale(app: Application, pet: Sprite) {
  const displayHeight = Math.min(app.renderer.height, app.renderer.width) * PET_DISPLAY_HEIGHT_RATIO;
  const textureHeight = pet.texture.height || 1;
  return displayHeight / textureHeight;
}

function getMotionFrame(
  stateId: PetStateId,
  motion: (typeof PET_STATES)[PetStateId]["motion"],
  elapsed: number
): MotionFrame {
  switch (motion) {
    case "bounce":
      if (stateId === "message") {
        return {
          x: Math.sin(elapsed / 430) * 0.8,
          y: Math.sin(elapsed / 280) * 3,
          rotation: Math.sin(elapsed / 360) * 0.012,
          scaleX: 1 - Math.sin(elapsed / 360) * 0.006,
          scaleY: 1 + Math.sin(elapsed / 360) * 0.012,
          alpha: 1
        };
      }

      return {
        x: Math.sin(elapsed / 520) * 1.2,
        y: -Math.abs(Math.sin(elapsed / 260)) * 5,
        rotation: Math.sin(elapsed / 390) * 0.018,
        scaleX: 1 - Math.sin(elapsed / 300) * 0.01,
        scaleY: 1 + Math.sin(elapsed / 300) * 0.018,
        alpha: 1
      };
    case "drowsy":
      return {
        x: Math.sin(elapsed / 1800) * 0.7,
        y: Math.sin(elapsed / 1050) * 1.8,
        rotation: Math.sin(elapsed / 1300) * 0.016,
        scaleX: 1,
        scaleY: 1,
        alpha: 1
      };
    case "shake":
      if (stateId === "weakSignal") {
        return {
          x: Math.sin(elapsed / 115) * 1.8,
          y: Math.sin(elapsed / 520) * 1.2,
          rotation: Math.sin(elapsed / 95) * 0.012,
          scaleX: 1,
          scaleY: 1,
          alpha: 0.9 + Math.sin(elapsed / 180) * 0.08
        };
      }

      return {
        x: Math.sin(elapsed / 70) * 1.4,
        y: Math.sin(elapsed / 80) * 2,
        rotation: Math.sin(elapsed / 55) * 0.018,
        scaleX: 1,
        scaleY: 1,
        alpha: 0.94 + Math.sin(elapsed / 110) * 0.06
      };
    case "sleep":
      return {
        x: 0,
        y: Math.sin(elapsed / 1050) * 1.5,
        rotation: 0,
        scaleX: 1 - Math.sin(elapsed / 1000) * 0.008,
        scaleY: 1 + Math.sin(elapsed / 1000) * 0.018,
        alpha: 1
      };
    case "drag":
      return {
        x: Math.sin(elapsed / 160) * 0.6,
        y: Math.sin(elapsed / 180) * 3,
        rotation: -0.12 + Math.sin(elapsed / 170) * 0.02,
        scaleX: 1,
        scaleY: 1,
        alpha: 1
      };
    case "pulse":
      if (stateId === "thinking") {
        return {
          x: Math.sin(elapsed / 1500) * 0.8,
          y: Math.sin(elapsed / 760) * 2.4,
          rotation: Math.sin(elapsed / 1200) * 0.012,
          scaleX: 1 - Math.sin(elapsed / 760) * 0.006,
          scaleY: 1 + Math.sin(elapsed / 760) * 0.012,
          alpha: 1
        };
      }

      return {
        x: 0,
        y: Math.sin(elapsed / 520) * 2.6,
        rotation: 0,
        scaleX: 1 - Math.sin(elapsed / 420) * 0.008,
        scaleY: 1 + Math.sin(elapsed / 420) * 0.014,
        alpha: 1
      };
    default:
      return {
        x: Math.sin(elapsed / 1800) * 0.7,
        y: Math.sin(elapsed / 850) * 2.3,
        rotation: Math.sin(elapsed / 1450) * 0.006,
        scaleX: 1 - Math.sin(elapsed / 950) * 0.005,
        scaleY: 1 + Math.sin(elapsed / 950) * 0.011,
        alpha: 1
      };
  }
}

function getStateTransitionFrame(ageMs: number): MotionFrame {
  if (ageMs < 0 || ageMs > 280) {
    return {
      x: 0,
      y: 0,
      rotation: 0,
      scaleX: 1,
      scaleY: 1,
      alpha: 1
    };
  }

  const progress = easeOutCubic(ageMs / 280);
  const pop = Math.sin(progress * Math.PI);
  return {
    x: 0,
    y: -6 * (1 - progress),
    rotation: 0,
    scaleX: 1 + pop * 0.035,
    scaleY: 1 - pop * 0.018,
    alpha: 0.86 + progress * 0.14
  };
}

function easeOutCubic(value: number) {
  return 1 - Math.pow(1 - Math.min(1, Math.max(0, value)), 3);
}
