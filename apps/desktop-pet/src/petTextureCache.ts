import { Assets, Texture } from "pixi.js";

import { PET_STATES, type PetStateId } from "./petStates";

const INITIAL_PRELOAD_STATE_IDS: readonly PetStateId[] = [
  "idle",
  "message",
  "happy",
  "pet",
  "loading",
  "weakSignal"
];

const FALLBACK_STATE_ID: PetStateId = "idle";

export type PetTextureCache = {
  textures: Partial<Record<PetStateId, Texture>>;
  pendingLoads: Partial<Record<PetStateId, Promise<Texture>>>;
};

export function createPetTextureCache(): PetTextureCache {
  return {
    textures: {},
    pendingLoads: {}
  };
}

export async function loadPetTexture(cache: PetTextureCache, stateId: PetStateId): Promise<Texture> {
  const cachedTexture = cache.textures[stateId];
  if (cachedTexture) return cachedTexture;

  const pendingLoad = cache.pendingLoads[stateId];
  if (pendingLoad) return pendingLoad;

  const loadPromise = Assets.load<Texture>(PET_STATES[stateId].assetUrl)
    .then((texture) => cacheTexture(cache, stateId, texture))
    .catch((error: unknown) => {
      delete cache.pendingLoads[stateId];
      console.warn(`Failed to load pet texture "${stateId}".`, error);

      if (stateId !== FALLBACK_STATE_ID) {
        return loadPetTexture(cache, FALLBACK_STATE_ID).then((fallbackTexture) => cacheTexture(cache, stateId, fallbackTexture));
      }

      return cacheTexture(cache, stateId, Texture.EMPTY);
    });
  cache.pendingLoads[stateId] = loadPromise;
  return loadPromise;
}

export function preloadInitialPetTextures(cache: PetTextureCache, currentStateId: PetStateId): void {
  const stateIds = new Set<PetStateId>([currentStateId, ...INITIAL_PRELOAD_STATE_IDS]);
  for (const stateId of stateIds) {
    void loadPetTexture(cache, stateId);
  }
}

function cacheTexture(cache: PetTextureCache, stateId: PetStateId, texture: Texture): Texture {
  cache.textures[stateId] = texture;
  delete cache.pendingLoads[stateId];
  return texture;
}
