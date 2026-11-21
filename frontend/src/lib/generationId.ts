/**
 * Generation ID counter — extracted into its own zero-dependency module
 * to break the circular import between stopController ↔ ttsManager ↔ chatManager.
 *
 * Every module can safely import this at any point during initialisation
 * because it has no side-effect imports of its own.
 */

let currentGenerationId = 0;

export function getNextGenerationId(): number {
    return ++currentGenerationId;
}

export function getCurrentGenerationId(): number {
    return currentGenerationId;
}
