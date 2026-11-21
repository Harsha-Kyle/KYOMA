import { BaseTTSProvider } from "./baseTTSProvider";
import { apiFetch } from "../api-client";

export interface TTSVoice {
    name: string;
    displayName?: string;
}

type GPTSoVITSStateUpdateCallback = () => void;

export class GPTSoVITSProvider extends BaseTTSProvider {
    private currentVoice: string | null = null;
    private voices: TTSVoice[] = [];
    private subscribers = new Set<GPTSoVITSStateUpdateCallback>();

    constructor() {
        super();
        this.initialize();
    }

    private async initialize() {
        await this.fetchVoices();
    }

    // Add public method to refresh voices
    async refreshVoices(): Promise<void> {
        await this.fetchVoices();
    }

    subscribe(callback: GPTSoVITSStateUpdateCallback): () => void {
        this.subscribers.add(callback);
        return () => this.subscribers.delete(callback);
    }

    private notifySubscribers() {
        this.subscribers.forEach(callback => callback());
    }

    private async fetchVoices() {
        try {
            const response = await apiFetch('/api/tts/voices');
            if (!response.ok) return;
            const data = await response.json();
            if (data?.voices && Array.isArray(data.voices)) {
                this.voices = data.voices.map((voice: string) => ({ name: voice }));
                this.notifySubscribers();
            }
        } catch (e) {
            console.warn('[GPTSoVITSProvider] Voices endpoint not available yet:', e);
        }
    }

    getVoices(): TTSVoice[] {
        return this.voices;
    }

    getCurrentVoice(): string | null {
        return this.currentVoice;
    }

    async setVoice(voice: string): Promise<void> {
        const response = await apiFetch('/api/tts/change-voice', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ voice_name: voice })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Failed to change voice');
        }

        this.currentVoice = voice;
        this.notifySubscribers();
    }

    async generateAudio(text: string): Promise<Response> {
        const response = await apiFetch("/api/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text })
        });

        if (!response.ok) {
            throw new Error("GPT-SoVITS generation failed");
        }

        return response;
    }
}