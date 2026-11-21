import { getApiKey } from "@/lib/api-client";
import { globalStateManager } from "@/lib/globalStateManager";
import { pipelineManager } from "@/lib/pipelineManager";

type AudioMessageListener = (data: any) => void;

class AudioWebSocketService {
  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private backoffDelay: number = 1000; // start at 1s
  private isIntentionallyClosed: boolean = false;
  private listeners: Set<AudioMessageListener> = new Set();
  private isTTSPlaying: boolean = false;
  private isLLMThinking: boolean = false;

  constructor() {
    globalStateManager.subscribe("isTTSPlaying", (val) => {
      this.isTTSPlaying = val;
    });
    globalStateManager.subscribe("isLLMThinking", (val) => {
      this.isLLMThinking = val;
    });
  }

  public subscribe(listener: AudioMessageListener): () => void {
    this.listeners.add(listener);
    // Connect if not already connected or connecting
    this.connect();

    return () => {
      this.listeners.delete(listener);
    };
  }

  public connect(): void {
    if (this.socket && (this.socket.readyState === WebSocket.CONNECTING || this.socket.readyState === WebSocket.OPEN)) {
      return;
    }

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    this.isIntentionallyClosed = false;
    const key = getApiKey();
    const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${wsProtocol}://${window.location.host}/ws/audio${key ? `?api_key=${encodeURIComponent(key)}` : ""}`;

    try {
      this.socket = new WebSocket(wsUrl);
    } catch (err) {
      console.warn("[AudioWS] Connection failed to construct:", err);
      this.scheduleReconnect();
      return;
    }

    this.socket.onopen = () => {
      console.log("[AudioWS] Connected successfully.");
      this.backoffDelay = 1000; // Reset backoff on successful open
    };

    this.socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "input_mode" && data.input_mode) {
          globalStateManager.updateState("inputMode", data.input_mode);
        } else if (data.type === "transcription") {
          if (this.isTTSPlaying || this.isLLMThinking) {
            console.log("[AudioWS] Ignored transcript during speech/thinking:", data.text);
            return;
          }
          const text = (data.text || "").trim();
          const alphanumericOnly = text.replace(/[^\w\s]/gi, "").trim();
          if (!alphanumericOnly) {
            console.log("[AudioWS] Discarded noise/dot transcript:", text);
            return;
          }
          pipelineManager.addInputTask(text);
        }

        // Notify UI listeners (e.g. probability or transcriptions list)
        this.listeners.forEach((listener) => {
          try {
            listener(data);
          } catch (e) {
            console.error("[AudioWS] Listener callback error:", e);
          }
        });
      } catch (e) {
        console.warn("[AudioWS] Message parse error:", e);
      }
    };

    this.socket.onerror = (err) => {
      console.warn("[AudioWS] WebSocket error:", err);
    };

    this.socket.onclose = () => {
      this.socket = null;
      if (!this.isIntentionallyClosed) {
        console.log(`[AudioWS] Connection closed unexpectedly. Reconnecting in ${this.backoffDelay}ms...`);
        this.scheduleReconnect();
      }
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer || this.isIntentionallyClosed) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, this.backoffDelay);

    // Exponential backoff: 1s, 2s, 4s, 8s, max 10s
    this.backoffDelay = Math.min(this.backoffDelay * 2, 10000);
  }

  public close(): void {
    this.isIntentionallyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.onclose = null;
      this.socket.onerror = null;
      this.socket.onmessage = null;
      this.socket.onopen = null;
      this.socket.close();
      this.socket = null;
    }
  }
}

export const audioWebSocketService = new AudioWebSocketService();
