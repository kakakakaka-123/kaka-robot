import { Application, Assets, Sprite, Texture } from "pixi.js";
import { useEffect, useRef } from "react";

import { PET_STATES, type PetStateId } from "./petStates";

const PET_DISPLAY_HEIGHT = 220;
const BASELINE_OFFSET = 8;

type PetCanvasProps = {
  stateId: PetStateId;
};

type MountedPet = {
  app: Application;
  pet: Sprite;
  textures: Record<PetStateId, Texture>;
};

export function PetCanvas({ stateId }: PetCanvasProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mountedPetRef = useRef<MountedPet | null>(null);
  const stateIdRef = useRef(stateId);

  useEffect(() => {
    stateIdRef.current = stateId;
    const mountedPet = mountedPetRef.current;
    if (mountedPet) {
      mountedPet.pet.texture = mountedPet.textures[stateId];
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

      const textures = Object.fromEntries(
        await Promise.all(
          Object.values(PET_STATES).map(async (state) => [state.id, await Assets.load<Texture>(state.assetUrl)] as const)
        )
      ) as Record<PetStateId, Texture>;
      if (destroyed) return;

      const pet = new Sprite(textures[stateIdRef.current]);
      pet.anchor.set(0.5, 1);
      pet.height = PET_DISPLAY_HEIGHT;
      pet.scale.x = pet.scale.y;
      pet.x = app.renderer.width / 2;
      pet.y = app.renderer.height - BASELINE_OFFSET;
      app.stage.addChild(pet);
      mountedPetRef.current = { app, pet, textures };

      app.ticker.add(() => {
        const elapsed = window.performance.now();
        const state = PET_STATES[stateIdRef.current];
        const motion = getMotionFrame(state.motion, elapsed);
        pet.x = app.renderer.width / 2;
        pet.y = app.renderer.height - BASELINE_OFFSET + motion.y;
        pet.rotation = motion.rotation;
        pet.alpha = motion.alpha;
        pet.scale.x = pet.scale.y * motion.scale;
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

function getMotionFrame(
  motion: (typeof PET_STATES)[PetStateId]["motion"],
  elapsed: number
): { y: number; rotation: number; scale: number; alpha: number } {
  switch (motion) {
    case "bounce":
      return {
        y: Math.sin(elapsed / 130) * 7,
        rotation: Math.sin(elapsed / 170) * 0.025,
        scale: 1 + Math.sin(elapsed / 160) * 0.015,
        alpha: 1
      };
    case "drowsy":
      return {
        y: Math.sin(elapsed / 950) * 2,
        rotation: Math.sin(elapsed / 1150) * 0.018,
        scale: 1,
        alpha: 1
      };
    case "shake":
      return {
        y: Math.sin(elapsed / 75) * 2,
        rotation: Math.sin(elapsed / 55) * 0.018,
        scale: 1,
        alpha: 0.94 + Math.sin(elapsed / 110) * 0.06
      };
    case "sleep":
      return {
        y: Math.sin(elapsed / 1050) * 1.5,
        rotation: 0,
        scale: 1 + Math.sin(elapsed / 1000) * 0.018,
        alpha: 1
      };
    case "drag":
      return {
        y: Math.sin(elapsed / 180) * 3,
        rotation: -0.12 + Math.sin(elapsed / 170) * 0.02,
        scale: 1,
        alpha: 1
      };
    case "pulse":
      return {
        y: Math.sin(elapsed / 520) * 3,
        rotation: 0,
        scale: 1 + Math.sin(elapsed / 420) * 0.014,
        alpha: 1
      };
    default:
      return {
        y: Math.sin(elapsed / 720) * 3,
        rotation: 0,
        scale: 1,
        alpha: 1
      };
  }
}
