import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Panel } from "./panel";
import { ScrollArea } from "@/components/ui/scroll-area";

import { pipelineManager } from "@/lib/pipelineManager";
import { globalStateManager } from "@/lib/globalStateManager";
import { apiFetch } from "@/lib/api-client";
import { audioWebSocketService } from "@/lib/audioWebSocketService";

export default function VoiceStreamer() {
  const [isRecording, setIsRecording] = useState(false);
  const [probability, setProbability] = useState<number | null>(null);
  const [transcriptions, setTranscriptions] = useState<string[]>([]);
  const isTTSPlayingRef = useRef<boolean>(false);
  const isLLMThinkingRef = useRef<boolean>(false);

  // ── Turn-level mute lifecycle ─────────────────────────────────────────────
  // A "turn" starts when the LLM begins thinking for a voice command and ends
  // when the final chunk has played back and the queue is empty.
  // We mute exactly once at turn start and unmute exactly once at turn end,
  // regardless of how many chunk gaps exist between TTS segments.
  const turnActiveRef = useRef<boolean>(false);
  const muteIssuedRef = useRef<boolean>(false);
  // Track the previous pipeline task ID so we can detect a new turn
  const lastTaskIdRef = useRef<string | null>(null);

  useEffect(() => {
    let prevRecording: boolean | null = null;
    // Subscribe to global recording state
    const unsubscribe = globalStateManager.subscribe('isVoiceRecording', async (recording) => {
      setIsRecording(recording);
      if (prevRecording === null) {
        // Initial subscription callback: only make an API call if recording is actually true
        prevRecording = recording;
        if (recording) {
          await apiFetch("/api/record/start", { method: "POST" });
        }
        return;
      }
      if (prevRecording === recording) return;
      prevRecording = recording;

      // Make appropriate API calls based on recording state transition
      if (recording) {
        await apiFetch("/api/record/start", { method: "POST" });
      } else {
        await apiFetch("/api/record/stop", { method: "POST" });
        // End any active turn when recording stops
        turnActiveRef.current = false;
        muteIssuedRef.current = false;
      }
    });

    // Set initial state
    setIsRecording(globalStateManager.getState('isVoiceRecording'));

    return () => unsubscribe();
  }, []);

  // ── Turn-level mute/unmute based on pipeline task state ──────────────────
  // Poll pipeline manager every 200ms to track turn lifecycle precisely.
  // This avoids mute/unmute churn between chunks.
  useEffect(() => {
    isTTSPlayingRef.current = globalStateManager.getState('isTTSPlaying');
    isLLMThinkingRef.current = globalStateManager.getState('isLLMThinking');

    const unsubTTS = globalStateManager.subscribe('isTTSPlaying', (playing) => {
      isTTSPlayingRef.current = playing;
    });
    const unsubLLM = globalStateManager.subscribe('isLLMThinking', (thinking) => {
      isLLMThinkingRef.current = thinking;
    });

    // Interval-based turn lifecycle manager
    const intervalId = setInterval(async () => {
      if (!globalStateManager.getState('isVoiceRecording')) return;

      const currentTask = pipelineManager.getCurrentTask();
      const isThinking = isLLMThinkingRef.current;
      const isPlaying = isTTSPlayingRef.current;

      // Detect new turn: a new active task has appeared
      if (currentTask && currentTask.id !== lastTaskIdRef.current) {
        lastTaskIdRef.current = currentTask.id;
        // Fresh task – start of a new turn
        if (!turnActiveRef.current) {
          turnActiveRef.current = true;
          muteIssuedRef.current = false;
        }
      }

      if (turnActiveRef.current) {
        // Mute exactly once at turn start
        if (!muteIssuedRef.current && (isThinking || isPlaying)) {
          muteIssuedRef.current = true;
          await apiFetch('/api/record/mute', { method: 'POST' }).catch(() => {});
        }

        // Determine if the turn is complete:
        // No active task AND neither thinking nor playing
        const taskDone = !currentTask ||
          currentTask.status === 'task_finished' ||
          currentTask.status === 'cancelled';
        const turnComplete = taskDone && !isThinking && !isPlaying;

        if (turnComplete && muteIssuedRef.current) {
          // Turn ended — wait 500ms post-playback guard before unmuting mic
          turnActiveRef.current = false;
          muteIssuedRef.current = false;
          setTimeout(async () => {
            await apiFetch('/api/record/unmute', { method: 'POST' }).catch(() => {});
          }, 500);
        }
      }
    }, 200);

    return () => {
      unsubTTS();
      unsubLLM();
      clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    const unsubscribe = audioWebSocketService.subscribe((data) => {
      if (data.type === "probability") {
        setProbability(data.probability);
      } else if (data.type === "transcription") {
        const text = (data.text || "").trim();
        const alphanumericOnly = text.replace(/[^\w\s]/gi, "").trim();
        if (alphanumericOnly) {
          setTranscriptions((prev) => [...prev, text]);
        }
      }
    });

    return () => {
      unsubscribe();
    };
  }, []);

  const startRecording = async () => {
    globalStateManager.updateState('isVoiceRecording', true);
  };

  const stopRecording = async () => {
    globalStateManager.updateState('isVoiceRecording', false);
  };



  return (
    <Panel className="max-w-4xl mx-auto">
      <h2 className="text-xl font-bold mb-4">Voice Input</h2>
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2">
          <Button className=" max-w-1/2"
            variant={`${isRecording ? "destructive" : "outline"}`}
            onClick={isRecording ? stopRecording : startRecording}
          >
            {isRecording ? "Stop Voice" : "Start Voice"}
          </Button>
          <div className="w-full">
            <p className="text-sm mb-1">Speech Probability:</p>
            <div className="w-full bg-gray-500 rounded-full h-2">
              <div
                className="bg-accent-foreground h-2 rounded-full"
                style={{ width: `${(probability ?? 0) * 100}%` }}
              ></div>
            </div>
            <p className="text-xs mt-1 text-right">
              {probability ? `${(probability * 100).toFixed(2)}%` : "--"}
            </p>
          </div>
        </div>

        <Panel className="h-186">
          <ScrollArea className="h-full overflow-auto">
            <Table className="">
              <TableHeader>
                <TableRow>
                  <TableHead className="">Transcriptions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...transcriptions].reverse().map((text, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-medium">{text}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </Panel>
      </div>
    </Panel>
  );
}
