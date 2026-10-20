import { BaseTTSProvider } from "./baseTTSProvider";
import { apiFetch } from "../api-client";

export interface KokoroVoice {
    id: string;
    display: string;
    lang: string;
}

type KokoroStateUpdateCallback = () => void;

export class KokoroProvider extends BaseTTSProvider {
    private currentVoice: string | null = null;
    private voices: KokoroVoice[] = [];
    private speed: number = 1.0;
    private subscribers = new Set<KokoroStateUpdateCallback>();

    constructor() {
        super();
        this.initialize();
    }

    private async initialize() {
        await this.fetchVoices();
    }

    async refreshVoices(): Promise<void> {
        await this.fetchVoices();
    }

    subscribe(callback: KokoroStateUpdateCallback): () => void {
        this.subscribers.add(callback);
        return () => this.subscribers.delete(callback);
    }

    private notifySubscribers() {
        this.subscribers.forEach(cb => cb());
    }

    private async fetchVoices() {
        try {
            const response = await apiFetch("/api/tts/kokoro/voices");
            const data = await response.json();
            this.voices = data.voices ?? [];
            if (data.current_voice) {
                this.currentVoice = data.current_voice;
            } else if (this.voices.length > 0 && !this.currentVoice) {
                this.currentVoice = this.voices[0].id;
            }
            this.notifySubscribers();
        } catch (e) {
            console.error("[KokoroProvider] Failed to fetch voices:", e);
        }
    }

    getVoices(): KokoroVoice[] {
        return this.voices;
    }

    getCurrentVoice(): string | null {
        return this.currentVoice;
    }

    getSpeed(): number {
        return this.speed;
    }

    /** Change voice — uses the generic /api/tts/change-voice endpoint */
    async setVoice(voiceId: string): Promise<void> {
        const response = await apiFetch("/api/tts/change-voice", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ voice_name: voiceId }),
        });
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || "Failed to change Kokoro voice");
        }
        this.currentVoice = voiceId;
        this.notifySubscribers();
    }

    /** Adjust playback speed (0.5 – 2.0) */
    async setSpeed(speed: number): Promise<void> {
        const response = await apiFetch("/api/tts/kokoro/speed", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ speed }),
        });
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || "Failed to set speed");
        }
        this.speed = speed;
        this.notifySubscribers();
    }

    /** Generate audio — calls the standard /api/tts endpoint */
    async generateAudio(text: string): Promise<Response> {
        const response = await apiFetch("/api/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });
        if (!response.ok) {
            throw new Error("Kokoro TTS generation failed");
        }
        return response;
    }
}
