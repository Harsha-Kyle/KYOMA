import { pipelineManager } from './pipelineManager';
import { globalStateManager } from './globalStateManager';
import { BaseTTSProvider } from './tts/baseTTSProvider';
import { GPTSoVITSProvider } from './tts/gptsovitsProvider';
import { RVCProvider } from './tts/rvcProvider';
import { KokoroProvider } from './tts/kokoroProvider';
import { apiFetch } from './api-client';
import { getCurrentGenerationId } from './generationId';

type TTSProvider = "gpt-sovits" | "rvc" | "kokoro";
type TTSUpdateCallback = () => void;

interface QueuedSynthesis {
    taskId: string;
    responseIndex: number;
    text: string;
    generationId: number;
    promise: Promise<string>;
}

export class TTSManager {
    private abortController: AbortController | null = null;
    private currentAudio: HTMLAudioElement | null = null;
    private isProcessing: boolean = false;
    private isPlaying: boolean = false;
    private selectedProvider: TTSProvider;
    private subscribers: Set<TTSUpdateCallback> = new Set();
    private providers: Record<TTSProvider, BaseTTSProvider>;
    public esp32Connected: boolean = false;

    // Prefetch queue and tracking
    private inFlightSynthesis: Map<string, QueuedSynthesis> = new Map();
    private lastChunkEndTime: number = 0;

    // Shared in-flight promise map and audio cache keyed by text, voice and speed
    private static audioCache: Map<string, string> = new Map();
    private static sharedInFlightRequests: Map<string, Promise<string>> = new Map();

    constructor() {
        const cached = (window as Window).__kyoma_settings_cache?.['tts.provider'] as TTSProvider | undefined;
        const validProviders: TTSProvider[] = ["gpt-sovits", "rvc", "kokoro"];
        this.selectedProvider = (cached && validProviders.includes(cached)) ? cached : "kokoro";
        this.providers = {
            "gpt-sovits": new GPTSoVITSProvider(),
            "rvc": new RVCProvider(),
            "kokoro": new KokoroProvider(),
        };
        this.setupPipelineSubscription();
    }

    public subscribe(callback: TTSUpdateCallback): () => void {
        this.subscribers.add(callback);
        return () => this.subscribers.delete(callback);
    }

    private notifySubscribers() {
        this.subscribers.forEach(callback => callback());
    }

    public getSelectedProvider(): TTSProvider {
        return this.selectedProvider;
    }

    public syncProviderFromCache(provider: TTSProvider) {
        if (["gpt-sovits", "rvc", "kokoro"].includes(provider) && this.selectedProvider !== provider) {
            this.selectedProvider = provider;
            this.notifySubscribers();
        }
    }

    public async setSelectedProvider(provider: TTSProvider) {
        try {
            await apiFetch("/api/tts/provider", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ provider }),
            });
        } catch (e) {
            console.error("[TTSManager] Failed to update backend provider:", e);
        }
        this.selectedProvider = provider;
        this.notifySubscribers();
    }

    public getCurrentProviderInstance(): BaseTTSProvider {
        return this.providers[this.selectedProvider];
    }

    private setupPipelineSubscription() {
        return pipelineManager.subscribe(() => {
            this.processNextTTS();
            this.processNextAudio();
            this.triggerPrefetch();
        });
    }

    private analyzeAudio(audio: HTMLAudioElement) {
        try {
            const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
            const audioContext = new AudioContextClass();
            const source = audioContext.createMediaElementSource(audio);
            const analyser = audioContext.createAnalyser();
            analyser.fftSize = 256;

            const dataArray = new Uint8Array(analyser.frequencyBinCount);
            source.connect(analyser);

            const gainNode = audioContext.createGain();
            gainNode.gain.value = this.esp32Connected ? 0 : 1;
            analyser.connect(gainNode);
            gainNode.connect(audioContext.destination);

            const updateVolume = () => {
                if (audio.paused || audio.ended) {
                    globalStateManager.updateState("ttsLiveVolume", 0);
                    return;
                }
                analyser.getByteFrequencyData(dataArray);
                const avgVolume = dataArray.reduce((a, b) => a + b, 0);
                const normalizedVolume = avgVolume / 15096;
                globalStateManager.updateState("ttsLiveVolume", normalizedVolume);
                requestAnimationFrame(updateVolume);
            };

            updateVolume();
        } catch (e) {
            console.debug("[TTSManager] AudioContext analysis error (ignorable):", e);
        }
    }

    private getCacheKey(text: string): string {
        const provider = this.getCurrentProviderInstance() as unknown as { getCurrentVoice?: () => string | null; getSpeed?: () => number };
        const voice = (typeof provider?.getCurrentVoice === 'function' ? provider.getCurrentVoice() : '') || 'default';
        const speed = (typeof provider?.getSpeed === 'function' ? provider.getSpeed() : 1.0) || 1.0;
        return `${this.selectedProvider}_${voice}_${speed}_${text.trim()}`;
    }

    public async generateAudioFromText(text: string): Promise<string> {
        const cacheKey = this.getCacheKey(text);

        // 1. Check shared audio cache
        if (TTSManager.audioCache.has(cacheKey)) {
            return TTSManager.audioCache.get(cacheKey)!;
        }

        // 2. Check in-flight promise map (deduplicate requests at source)
        if (TTSManager.sharedInFlightRequests.has(cacheKey)) {
            return TTSManager.sharedInFlightRequests.get(cacheKey)!;
        }

        const tTextReady = performance.now();
        const synthPromise = (async () => {
            try {
                const tReqSent = performance.now();
                const provider = this.getCurrentProviderInstance();
                const response = await provider.generateAudio(text);

                if (response.headers.get("X-ESP32-Connected") === "true") {
                    this.esp32Connected = true;
                } else {
                    this.esp32Connected = false;
                }

                const blob = await response.blob();
                const audioUrl = URL.createObjectURL(blob);
                const tSynthDone = performance.now();
                const elapsedMs = (tSynthDone - tReqSent).toFixed(0);
                const totalWaitMs = (tSynthDone - tTextReady).toFixed(0);
                console.log(`[TTSManager] Synthesized in ${elapsedMs}ms (total wait: ${totalWaitMs}ms): "${text.slice(0, 30)}..."`);

                // Cache repeated short fast responses where safe (up to 100 entries)
                if (TTSManager.audioCache.size < 100) {
                    TTSManager.audioCache.set(cacheKey, audioUrl);
                }
                return audioUrl;
            } finally {
                TTSManager.sharedInFlightRequests.delete(cacheKey);
            }
        })();

        TTSManager.sharedInFlightRequests.set(cacheKey, synthPromise);
        return synthPromise;
    }

    /**
     * Bounded prefetch: while chunk N is synthesizing or playing, proactively
     * synthesize chunk N+1 and N+2 in the background.
     */
    private triggerPrefetch() {
        const currentGenId = getCurrentGenerationId();
        const currentTask = pipelineManager.getCurrentTask();
        if (!currentTask || currentTask.status === "cancelled" || currentTask.status === "pending_interruption") {
            return;
        }

        // Look for responses that have text but no audio yet and are not currently in-flight
        for (let i = 0; i < currentTask.response.length; i++) {
            const resp = currentTask.response[i];
            const key = `${currentTask.id}_${i}`;
            if (resp.text && !resp.audio && !this.inFlightSynthesis.has(key)) {
                // Keep queue bounded to at most 2 concurrent syntheses
                if (this.inFlightSynthesis.size >= 2) break;

                const textToSpeak = resp.text;
                const genId = currentGenId;
                const promise = (async () => {
                    try {
                        const url = await this.generateAudioFromText(textToSpeak);
                        // Check generation ID on completion
                        if (getCurrentGenerationId() === genId) {
                            pipelineManager.addTTSAudio(currentTask.id, i, url);
                        } else {
                            URL.revokeObjectURL(url);
                        }
                        return url;
                    } catch (err) {
                        console.warn("[TTSManager] Prefetch error for chunk:", err);
                        return "";
                    } finally {
                        this.inFlightSynthesis.delete(key);
                    }
                })();

                this.inFlightSynthesis.set(key, {
                    taskId: currentTask.id,
                    responseIndex: i,
                    text: textToSpeak,
                    generationId: genId,
                    promise,
                });
            }
        }
    }

    private async processNextTTS() {
        const currentTask = pipelineManager.getCurrentTask();
        if (currentTask?.status === "pending_interruption" && !currentTask.interruptionState?.tts) {
            if (this.abortController) {
                this.abortController.abort();
            }
            this.isProcessing = false;
            pipelineManager.markInterruptionState("tts");
            return;
        }

        if (this.isProcessing) return;

        const next = pipelineManager.getNextTaskForTTS();
        if (!next) return;

        const { taskId, responseIndex, task } = next;
        const textToSpeak = task.response[responseIndex].text;
        const key = `${taskId}_${responseIndex}`;

        // If already being prefetched, let the in-flight prefetch complete
        if (this.inFlightSynthesis.has(key)) {
            return;
        }

        this.isProcessing = true;
        const genId = getCurrentGenerationId();

        try {
            const audioUrl = await this.generateAudioFromText(textToSpeak);
            if (getCurrentGenerationId() === genId) {
                pipelineManager.addTTSAudio(taskId, responseIndex, audioUrl);
            } else {
                URL.revokeObjectURL(audioUrl);
            }
        } catch (err) {
            console.error("TTS pipeline error:", err);
        } finally {
            this.isProcessing = false;
        }
    }

    private async processNextAudio() {
        const currentTask = pipelineManager.getCurrentTask();
        if (currentTask?.status === "pending_interruption" && !currentTask.interruptionState?.audio) {
            if (this.currentAudio) {
                this.currentAudio.pause();
                this.currentAudio.currentTime = 0;
                this.currentAudio = null;
            }
            this.isPlaying = false;
            globalStateManager.updateState("isTTSPlaying", false);
            pipelineManager.markInterruptionState("audio");
            return;
        }

        if (this.isPlaying) return;

        const next = pipelineManager.getNextTaskForAudio();
        if (!next) return;

        const { taskId, responseIndex, task } = next;
        const audioUrl = task.response[responseIndex].audio;
        if (!audioUrl) return;

        const genId = getCurrentGenerationId();

        // Calculate and log inter-chunk gap
        const now = performance.now();
        if (this.lastChunkEndTime > 0) {
            const gapMs = (now - this.lastChunkEndTime).toFixed(1);
            console.log(`[TTSManager] Inter-chunk gap: ${gapMs}ms`);
        }

        this.isPlaying = true;
        globalStateManager.updateState("isTTSPlaying", true);

        const audio = new Audio(audioUrl);
        this.currentAudio = audio;

        audio.play().catch(e => {
            console.warn("[TTSManager] audio.play() prevented or failed:", e);
        });
        this.analyzeAudio(audio);

        // While this audio is playing, ensure subsequent chunks are prefetching
        this.triggerPrefetch();

        audio.onended = () => {
            this.lastChunkEndTime = performance.now();
            this.isPlaying = false;
            this.currentAudio = null;
            globalStateManager.updateState("isTTSPlaying", false);

            if (getCurrentGenerationId() === genId) {
                pipelineManager.markPlaybackFinished(taskId, responseIndex);
            }
        };
    }

    public stopAllAudio() {
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.currentAudio = null;
        }
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
        this.isPlaying = false;
        this.isProcessing = false;
        this.inFlightSynthesis.clear();
        this.lastChunkEndTime = 0;

        globalStateManager.updateState("isTTSPlaying", false);
        globalStateManager.updateState("ttsLiveVolume", 0);
    }
}

export const ttsManager = new TTSManager();
