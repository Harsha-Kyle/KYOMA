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
    const [isTTSPlaying, setIsTTSPlaying] = useState<boolean>(false);

    useEffect(() => {
        const unsubscribe = globalStateManager.subscribe('isTTSPlaying', (playing) => {
            setIsTTSPlaying(playing);
        });
        setIsTTSPlaying(globalStateManager.getState('isTTSPlaying'));
        return () => unsubscribe();
    }, []);

    const handleStop = () => {
        ttsManager.stopAllAudio();
        chatManager.stopGeneration();
        pipelineManager.cancelAllTasks();
        pipelineManager.interruptCurrentTask();
        apiFetch('/api/record/unmute', { method: 'POST' }).catch(() => {});
        globalStateManager.updateState('isTTSPlaying', false);
        globalStateManager.updateState('isLLMThinking', false);
    };

    return (
        <div className="p-5">
            {isTTSPlaying && (
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