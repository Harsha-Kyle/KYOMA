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
import { ScrollArea } from "@radix-ui/react-scroll-area";

import { pipelineManager } from "@/lib/pipelineManager";
import { globalStateManager } from "@/lib/globalStateManager";
import { apiFetch, getApiKey } from "@/lib/api-client";

export default function VoiceStreamer() {
  const [isRecording, setIsRecording] = useState(false);
  const [probability, setProbability] = useState<number | null>(null);
  const [transcriptions, setTranscriptions] = useState<string[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
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
    // Subscribe to global recording state
    const unsubscribe = globalStateManager.subscribe('isVoiceRecording', async (recording) => {
      setIsRecording(recording);
      // Make appropriate API calls based on recording state
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
          // Turn ended — unmute exactly once
          turnActiveRef.current = false;
          muteIssuedRef.current = false;
          await apiFetch('/api/record/unmute', { method: 'POST' }).catch(() => {});
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
    const key = getApiKey();
    const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${wsProtocol}://${window.location.host}/ws/audio${key ? `?api_key=${encodeURIComponent(key)}` : ""}`;
    const socket = new WebSocket(wsUrl);

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "probability") {
        // DISABLED: prevent self-interruption during TTS playback
        /*
        if (data.probability >= 0.45 && !isTTSPlayingRef.current && pipelineManager.getCurrentTask()?.status != "pending_interruption"){
          pipelineManager.interruptCurrentTask()
        }
        */
        setProbability(data.probability);
      } else if (data.type === "transcription") {
        // Gate transcription: discard if TTS is playing OR LLM is actively thinking
        if (isTTSPlayingRef.current || isLLMThinkingRef.current) {
          console.log("[VoiceStreamer] Ignored transcript during speech/thinking:", data.text);
          return;
        }
        const text = (data.text || "").trim();
        // Discard dot-only noise e.g. ". . . . ." or empty/whitespace/punctuation-only strings
        const alphanumericOnly = text.replace(/[^\w\s]/gi, '').trim();
        if (!alphanumericOnly) {
          console.log("[VoiceStreamer] Silently discarded noise/dot transcript:", text);
          return;
        }
        pipelineManager.addInputTask(text);
        setTranscriptions((prev) => [...prev, text]);
      }

    };

    socketRef.current = socket;
    return () => {
      socket.close();
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
