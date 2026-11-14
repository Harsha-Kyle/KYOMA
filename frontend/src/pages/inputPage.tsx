import { useState, useEffect } from "react"
import VoiceStreamer from "@/components/voice-streamer"
import { Button } from "@/components/ui/button"
import { Square } from "lucide-react"
import { globalStateManager } from "@/lib/globalStateManager"
import { pipelineManager } from "@/lib/pipelineManager"
import { ttsManager } from "@/lib/ttsManager"
import { chatManager } from "@/lib/chatManager"
import { apiFetch } from "@/lib/api-client"

function InputPage() {
    // Show Stop button whenever the system is thinking OR speaking —
    // not just during TTS playback. This prevents the button from
    // disappearing in the gaps between chunks.
    const [turnActive, setTurnActive] = useState<boolean>(false);

    useEffect(() => {
        const updateTurnState = () => {
            const thinking = globalStateManager.getState('isLLMThinking');
            const playing = globalStateManager.getState('isTTSPlaying');
            // Turn is active if either thinking or playing, OR if there is a
            // non-finished pipeline task (covers inter-chunk gaps)
            const task = pipelineManager.getCurrentTask();
            const hasActiveTask = !!task &&
                task.status !== 'task_finished' &&
                task.status !== 'cancelled';
            setTurnActive(thinking || playing || hasActiveTask);
        };

        const unsubTTS = globalStateManager.subscribe('isTTSPlaying', updateTurnState);
        const unsubLLM = globalStateManager.subscribe('isLLMThinking', updateTurnState);
        // Also react to pipeline changes
        const unsubPipeline = pipelineManager.subscribe(updateTurnState);

        updateTurnState();
        return () => {
            unsubTTS();
            unsubLLM();
            unsubPipeline();
        };
    }, []);

    // Turn ID guard: assign a new ID when Stop is pressed so that any
    // in-flight async callbacks (TTS fetch completions, audio onended) know
    // they belong to a cancelled turn and must not trigger unmute or further
    // pipeline state changes.
    const handleStop = () => {
        ttsManager.stopAllAudio();
        chatManager.stopGeneration();
        pipelineManager.cancelAllTasks();
        pipelineManager.interruptCurrentTask();
        // Unmute exactly once after all queued audio and pending TTS are cleared
        apiFetch('/api/record/unmute', { method: 'POST' }).catch(() => {});
        globalStateManager.updateState('isTTSPlaying', false);
        globalStateManager.updateState('isLLMThinking', false);
        setTurnActive(false);
    };

    return (
        <div className="p-5">
            {turnActive && (
                <div className="flex justify-center mb-4">
                    <Button
                        variant="destructive"
                        size="icon"
                        title="Stop Speaking / Interrupt (or press .)"
                        onClick={handleStop}
                    >
                        <Square className="h-5 w-5" />
                    </Button>
                </div>
            )}
            <VoiceStreamer></VoiceStreamer>
        </div>
    )
}

  
  export default InputPage