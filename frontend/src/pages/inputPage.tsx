import { useState, useEffect } from "react"
import VoiceStreamer from "@/components/voice-streamer"
import { Button } from "@/components/ui/button"
import { Square } from "lucide-react"
import { globalStateManager } from "@/lib/globalStateManager"
import { pipelineManager } from "@/lib/pipelineManager"
import { stopAll } from "@/lib/stopController"

function InputPage() {
    const [turnActive, setTurnActive] = useState<boolean>(false);

    useEffect(() => {
        const updateTurnState = () => {
            const thinking = globalStateManager.getState('isLLMThinking');
            const playing = globalStateManager.getState('isTTSPlaying');
            const task = pipelineManager.getCurrentTask();
            const hasActiveTask = !!task &&
                task.status !== 'task_finished' &&
                task.status !== 'cancelled';
            setTurnActive(thinking || playing || hasActiveTask);
        };

        const unsubTTS = globalStateManager.subscribe('isTTSPlaying', updateTurnState);
        const unsubLLM = globalStateManager.subscribe('isLLMThinking', updateTurnState);
        const unsubPipeline = pipelineManager.subscribe(updateTurnState);

        updateTurnState();
        return () => {
            unsubTTS();
            unsubLLM();
            unsubPipeline();
        };
    }, []);

    const handleStop = () => {
        stopAll().catch(() => {});
        setTurnActive(false);
    };

    return (
        <div className="h-full overflow-y-auto p-5">
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
