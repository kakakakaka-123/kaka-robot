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

  const loadPromise = Assets.load<Texture>(PET_STATES[stateId].assetUrl).then((texture) => {
    cache.textures[stateId] = texture;
    delete cache.pendingLoads[stateId];
    return texture;
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
