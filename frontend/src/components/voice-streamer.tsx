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

  useEffect(() => {
    // Subscribe to global recording state
    const unsubscribe = globalStateManager.subscribe('isVoiceRecording', async (recording) => {
      setIsRecording(recording);
      // Make appropriate API calls based on recording state
      if (recording) {
        await apiFetch("/api/record/start", { method: "POST" });
      } else {
        await apiFetch("/api/record/stop", { method: "POST" });
      }
    });

    // Set initial state
    setIsRecording(globalStateManager.getState('isVoiceRecording'));

    return () => unsubscribe();
  }, []);

  // Keep isTTSPlayingRef and isLLMThinkingRef in sync with globalStateManager
  useEffect(() => {
    const unsubTTS = globalStateManager.subscribe('isTTSPlaying', async (playing) => {
      isTTSPlayingRef.current = playing;
      if (globalStateManager.getState('isVoiceRecording')) {
        if (playing) {
          await apiFetch('/api/record/mute', { method: 'POST' });
        } else if (!globalStateManager.getState('isLLMThinking')) {
          await apiFetch('/api/record/unmute', { method: 'POST' });
        }
      }
    });

    const unsubLLM = globalStateManager.subscribe('isLLMThinking', async (thinking) => {
      isLLMThinkingRef.current = thinking;
      if (globalStateManager.getState('isVoiceRecording')) {
        if (thinking) {
          await apiFetch('/api/record/mute', { method: 'POST' });
        } else if (!globalStateManager.getState('isTTSPlaying')) {
          await apiFetch('/api/record/unmute', { method: 'POST' });
        }
      }
    });

    isTTSPlayingRef.current = globalStateManager.getState('isTTSPlaying');
    isLLMThinkingRef.current = globalStateManager.getState('isLLMThinking');

    return () => {
      unsubTTS();
      unsubLLM();
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
