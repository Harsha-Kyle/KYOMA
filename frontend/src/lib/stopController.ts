import { chatManager } from './chatManager';
import { pipelineManager } from './pipelineManager';
import { ttsManager } from './ttsManager';
import { globalStateManager } from './globalStateManager';
import { apiFetch } from './api-client';
// Re-export from the zero-dependency module so existing consumers don't break
export { getCurrentGenerationId, getNextGenerationId } from './generationId';
import { getNextGenerationId } from './generationId';

/**
 * Single unified stop controller for all Stop buttons and hotkeys across the UI.
 * Immediately halts LLM generation, clears active audio, cancels queued pipeline tasks,
 * invalidates late/pre-fetched chunks via generation ID, resets UI states,
 * and requests backend playback silence without modifying scheduled reminders.
 */
export async function stopAll(): Promise<void> {
    // 1. Advance generation ID so any in-flight or late-arriving responses are dropped
    const newGenId = getNextGenerationId();
    console.log(`[StopController] stopAll invoked. Invalidation Generation ID -> ${newGenId}`);

    // 2. Stop active assistant audio and clear queued TTS
    try {
        ttsManager.stopAllAudio();
    } catch (e) {
        console.error("[StopController] Error stopping TTS audio:", e);
    }

    // 3. Abort in-flight LLM completion and generation stream
    try {
        chatManager.stopGeneration();
    } catch (e) {
        console.error("[StopController] Error stopping chatManager generation:", e);
    }

    // 4. Cancel all tasks in pipeline
    try {
        pipelineManager.cancelAllTasks();
        pipelineManager.interruptCurrentTask();
    } catch (e) {
        console.error("[StopController] Error cancelling pipeline tasks:", e);
    }

    // 5. Reset UI states & remove stale thinking indicator immediately
    globalStateManager.updateState('isTTSPlaying', false);
    globalStateManager.updateState('isLLMThinking', false);
    globalStateManager.updateState('ttsLiveVolume', 0);

    // 6. Request backend to silence audio playback (winsound / reminder playback) and unmute mic ASYNCHRONOUSLY.
    // Do NOT await backend shutdown before returning; UI must restore usability instantly.
    apiFetch('/api/audio/stop', { method: 'POST' }).catch(() => {
        apiFetch('/api/record/unmute', { method: 'POST' }).catch(() => {});
    });
}
