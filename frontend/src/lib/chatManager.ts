import { splitIntoSpokenSentences } from './tts-sanitizer';
import { HistoryItem } from './types';
import { pipelineManager } from './pipelineManager';
import { createNewSession, updateSession, fetchSessionContent } from './sessionManager';
import { apiFetch } from './api-client';
import { globalStateManager } from './globalStateManager';
import { getCurrentGenerationId, getNextGenerationId } from './generationId';

type ChatUpdateCallback = (messages: HistoryItem[]) => void;

interface SubscriptionOptions {
    onMessagesChange?: boolean;
    onSystemPromptChange?: boolean;
    onVisionPromptChange?: boolean;
    onOcrPromptChange?: boolean;
    onImageChange?: boolean;
    onContextChange?: boolean;
    onFullSystemPromptChange?: boolean;
}

export class ChatManager {
    private messages: HistoryItem[] = [];
    private sessionId: string | null = null;
    private abortController: AbortController | null = null;
    private systemPrompt: string = '';
    private visionPrompt: string = '';
    private ocrPrompt: string = '';
    private currentImage: string = '';
    private retrievedContext: string = '';
    private fullSystemPrompt: string = '';
    private enableMemoryRetrieval: boolean = true;
    private subscribers: Map<ChatUpdateCallback, SubscriptionOptions> = new Map();

    constructor() {
        this.setupPipelineSubscription();
    }

    public subscribe(callback: ChatUpdateCallback, options: SubscriptionOptions = { onMessagesChange: true }): () => void {
        this.subscribers.set(callback, options);
        return () => this.subscribers.delete(callback);
    }

    private notifySubscribers(changeType: keyof SubscriptionOptions) {
        this.subscribers.forEach((options, callback) => {
            if (options[changeType]) {
                callback([...this.messages]);
            }
        });
    }

    public getSystemPrompt(): string {
        return this.systemPrompt;
    }

    public setSystemPrompt(systemPrompt: string) {
        this.systemPrompt = systemPrompt;
        this.notifySubscribers('onSystemPromptChange');
    }

    public getVisionPrompt(): string {
        return this.visionPrompt;
    }

    public setVisionPrompt(visionPrompt: string) {
        this.visionPrompt = visionPrompt;
        this.notifySubscribers('onVisionPromptChange');
    }

    public getOcrPrompt(): string {
        return this.ocrPrompt;
    }

    public setOcrPrompt(ocrPrompt: string) {
        this.ocrPrompt = ocrPrompt;
        this.notifySubscribers('onOcrPromptChange');
    }

    public getCurrentImage(): string {
        return this.currentImage;
    }

    public setCurrentImage(image: string) {
        this.currentImage = image;
        this.notifySubscribers('onImageChange');
    }

    public getRetrievedContext(): string {
        return this.retrievedContext;
    }

    public setRetrievedContext(context: string) {
        this.retrievedContext = context;
        this.notifySubscribers('onContextChange');
    }

    public setEnableMemoryRetrieval(enabled: boolean) {
        this.enableMemoryRetrieval = enabled;
        if (!enabled) {
            this.setRetrievedContext('');
        }
    }

    public getFullSystemPrompt(): string {
        return this.fullSystemPrompt;
    }

    public setFullSystemPrompt(prompt: string) {
        this.fullSystemPrompt = prompt;
        this.notifySubscribers('onFullSystemPromptChange');
    }

    private setupPipelineSubscription() {
        const handlePipelineUpdate = () => {
            this.handleInterrupt();
            const task = pipelineManager.getNextTaskForLLM();
            if (!task) return;
            const input = task.input!;
            this.sendMessage(input, task.id);
        };

        return pipelineManager.subscribe(handlePipelineUpdate);
    }

    /**
     * Generation-safe cleanup path across success, error, abort and stop.
     * Clears thinking state, prunes empty assistant placeholders, and notifies UI.
     */
    public finishTurn(genId?: number) {
        if (genId !== undefined && getCurrentGenerationId() !== genId) {
            return;
        }
        // Remove trailing empty assistant placeholder if present
        if (this.messages.length > 0 && this.messages[this.messages.length - 1].role === 'assistant') {
            const last = this.messages[this.messages.length - 1];
            if (!last.content || last.content.trim() === '') {
                this.messages.pop();
                this.notifySubscribers('onMessagesChange');
            }
        }
        globalStateManager.updateState('isLLMThinking', false);
    }

    public stopGeneration() {
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
        this.finishTurn();
    }

    public handleInterrupt() {
        const currentTask = pipelineManager.getCurrentTask();
        if (currentTask?.status === "pending_interruption" && !currentTask.interruptionState?.llm) {
            this.stopGeneration();
            pipelineManager.markInterruptionState("llm");
            return true;
        }
        return false;
    }

    public async sendMessage(
        input: string, 
        taskId: string | null = null,
    ): Promise<void> {
        if (input.trim() === '') return;
        if (!taskId) taskId = null;
        else pipelineManager.markLLMStarted(taskId);

        // Assign a new generation ID for this turn
        const genId = getNextGenerationId();
        this.abortController = new AbortController();
        const userMessage: HistoryItem = { role: 'user', content: input };

        // Maintain the last 4 user/assistant turns (8 messages) for LLM context, excluding transitory search acks
        const nonAckMessages = this.messages.filter(m => !m.content?.includes('<<<KYOMA_SEARCH_SPLIT>>>'));
        const history = nonAckMessages.slice(-8);
        
        this.messages.push(userMessage);
        this.notifySubscribers('onMessagesChange');
        globalStateManager.updateState('isLLMThinking', true);

        try {
            // Fetch relevant context from memory (if enabled)
            let contextText = '';
            if (this.enableMemoryRetrieval) {
                try {
                    const contextRes = await apiFetch('/api/memory/context', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ text: input, limit: 3 })
                    });
                    if (contextRes.ok) {
                        const contextData = await contextRes.json();
                        if (Array.isArray(contextData.context) && contextData.context.length > 0) {
                            contextText = contextData.context
                                .map((c: Record<string, unknown>) => typeof c.document === 'string' ? c.document : '')
                                .filter(Boolean)
                                .join('\n');
                        }
                    }
                } catch (ctxErr) {
                    console.warn('Failed to fetch context:', ctxErr);
                }
            } else {
                this.setRetrievedContext('');
            }

            // Check generation validity
            if (getCurrentGenerationId() !== genId) {
                console.log(`[ChatManager] Generation ${genId} cancelled before LLM request.`);
                this.finishTurn(genId);
                return;
            }

            // Assemble system prompt with labeled sections
            const visionSection = this.visionPrompt.trim() ? `[SCREEN CONTEXT]\n${this.visionPrompt}\n\n` : '';
            const ocrSection = this.ocrPrompt.trim() ? `[SCREEN TEXT]\n${this.ocrPrompt}\n\n` : '';
            const contextSection = contextText.trim() ? `[RETRIEVED MEMORY]\n${contextText}\n\n` : '';
            const instructionsSection = `[INSTRUCTIONS]\n${this.systemPrompt}\n\n`;
            const systemPromptWithContext = visionSection + ocrSection + contextSection + instructionsSection;

            this.setRetrievedContext(contextText);
            this.setFullSystemPrompt(systemPromptWithContext);

            const response = await apiFetch('/api/completion', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: input,
                    history: history,
                    systemPrompt: systemPromptWithContext
                }),
                signal: this.abortController.signal
            });

            if (getCurrentGenerationId() !== genId) {
                console.log(`[ChatManager] Generation ${genId} cancelled during response arrival.`);
                this.finishTurn(genId);
                return;
            }

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                console.error("Error during completion:", errorData?.error);
                this.finishTurn(genId);
                return;
            }

            if (this.sessionId === null) {
                const newSessionId = await createNewSession();
                if (newSessionId) {
                    this.sessionId = newSessionId;
                }
            }

            await updateSession(this.sessionId, this.messages);

            // Push placeholder for the stream
            this.messages = [...this.messages, { role: 'assistant', content: '' }];
            this.notifySubscribers('onMessagesChange');

            const reader = response.body?.getReader();
            const decoder = new TextDecoder();
            let aiMessage = '';
            const SEARCH_DELIMITER = '<<<KYOMA_SEARCH_SPLIT>>>';
            let searchAckDelivered = false;
            let ackTaskId: string | null = null;
            let dispatchedSentenceCount = 0;
            
            if (!reader) {
                this.finishTurn(genId);
                return;
            }

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                // Stop check on each chunk
                if (getCurrentGenerationId() !== genId) {
                    reader.cancel();
                    console.log(`[ChatManager] Stream cancelled mid-flight for genId ${genId}`);
                    this.finishTurn(genId);
                    return;
                }
                
                const chunk = decoder.decode(value, { stream: true });
                aiMessage += chunk;

                // Check if search acknowledgement arrived before final answer
                if (!searchAckDelivered && aiMessage.includes(SEARCH_DELIMITER)) {
                    searchAckDelivered = true;
                    const parts = aiMessage.split(SEARCH_DELIMITER);
                    const ackText = parts[0].trim();

                    // Play acknowledgement speech immediately without saving it as permanent chat history
                    const ackChunks = splitIntoSpokenSentences(ackText);
                    for (const ch of ackChunks) {
                        if (ackTaskId === null) {
                            ackTaskId = pipelineManager.createTaskFromLLM(input, ch);
                        } else {
                            pipelineManager.addLLMResponse(ackTaskId, ch);
                        }
                    }
                    if (ackTaskId !== null) {
                        pipelineManager.markLLMFinished(ackTaskId);
                    }

                    // Reset assistant placeholder for upcoming actual answer content
                    const answerContent = (parts[1] || '').trimStart();
                    this.messages[this.messages.length - 1] = { role: 'assistant', content: answerContent };
                    this.notifySubscribers('onMessagesChange');
                } else if (searchAckDelivered) {
                    const parts = aiMessage.split(SEARCH_DELIMITER);
                    const answerContent = (parts[1] || '').trimStart();
                    this.messages[this.messages.length - 1] = { role: 'assistant', content: answerContent };
                    this.notifySubscribers('onMessagesChange');

                    // Stream-level TTS dispatch as sentences become ready
                    const candidateSentences = splitIntoSpokenSentences(answerContent);
                    if (candidateSentences.length > dispatchedSentenceCount + 1) {
                        // All sentences except the currently forming last sentence are complete
                        for (let sIdx = dispatchedSentenceCount; sIdx < candidateSentences.length - 1; sIdx++) {
                            const sent = candidateSentences[sIdx];
                            if (taskId === null) {
                                taskId = pipelineManager.createTaskFromLLM(input, sent);
                            } else {
                                pipelineManager.addLLMResponse(taskId, sent);
                            }
                            dispatchedSentenceCount++;
                        }
                    }
                } else {
                    this.messages[this.messages.length - 1] = { role: 'assistant', content: aiMessage };
                    this.notifySubscribers('onMessagesChange');

                    // Stream-level TTS dispatch as sentences become ready
                    const candidateSentences = splitIntoSpokenSentences(aiMessage);
                    if (candidateSentences.length > dispatchedSentenceCount + 1) {
                        for (let sIdx = dispatchedSentenceCount; sIdx < candidateSentences.length - 1; sIdx++) {
                            const sent = candidateSentences[sIdx];
                            if (taskId === null) {
                                taskId = pipelineManager.createTaskFromLLM(input, sent);
                            } else {
                                pipelineManager.addLLMResponse(taskId, sent);
                            }
                            dispatchedSentenceCount++;
                        }
                    }
                }
            }

            if (getCurrentGenerationId() !== genId) {
                this.finishTurn(genId);
                return;
            }

            // Speak final remaining sentences at stream end
            let finalToSpeak = aiMessage;
            if (searchAckDelivered) {
                const parts = aiMessage.split(SEARCH_DELIMITER);
                finalToSpeak = (parts[1] || '').trim();
            }

            if (finalToSpeak) {
                const spokenChunks = splitIntoSpokenSentences(finalToSpeak);
                for (let sIdx = dispatchedSentenceCount; sIdx < spokenChunks.length; sIdx++) {
                    const chunk = spokenChunks[sIdx];
                    if (taskId === null) {
                        taskId = pipelineManager.createTaskFromLLM(input, chunk);
                    } else {
                        pipelineManager.addLLMResponse(taskId, chunk);
                    }
                }
                if (taskId !== null) {
                    pipelineManager.markLLMFinished(taskId);
                }
            }
            
            await updateSession(this.sessionId, this.messages);
            this.notifySubscribers('onMessagesChange');

        } catch (error) {
            if ((error as Error).name === 'AbortError') {
                console.log('Fetch aborted');
            } else {
                console.error('Fetch error:', error);
            }
        } finally {
            this.finishTurn(genId);
        }
    }

    public async continueMessage(index: number) {
        const history = this.messages.slice(0, index + 1);
        const response = await apiFetch('/api/completion/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ history: history, systemPrompt: this.systemPrompt })
        });
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) return;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            this.messages[index].content += chunk;
            this.notifySubscribers('onMessagesChange');
        }
        await updateSession(this.sessionId, this.messages);
        this.notifySubscribers('onMessagesChange');
    }

    public async regenerateMessage(index: number) {
        if (this.messages[index].role !== 'assistant') return;
        
        const historyUpToMessage = this.messages.slice(0, index);
        const lastUserMessage = historyUpToMessage[historyUpToMessage.length - 1];
        if (!lastUserMessage || lastUserMessage.role !== 'user') return;

        this.messages[index].content = '';
        this.notifySubscribers('onMessagesChange');

        let contextText = '';
        if (this.enableMemoryRetrieval) {
            try {
                const contextRes = await apiFetch('/api/memory/context', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: lastUserMessage.content, limit: 3 })
                });
                if (contextRes.ok) {
                    const contextData = await contextRes.json();
                    if (Array.isArray(contextData.context) && contextData.context.length > 0) {
                        contextText = contextData.context
                            .map((c: Record<string, unknown>) => typeof c.document === 'string' ? c.document : '')
                            .filter(Boolean)
                            .join('\n');
                    }
                }
            } catch (ctxErr) {
                console.warn('Failed to fetch context:', ctxErr);
            }
        }

        const visionSection = this.visionPrompt.trim() ? `[SCREEN CONTEXT]\n${this.visionPrompt}\n\n` : '';
        const ocrSection = this.ocrPrompt.trim() ? `[SCREEN TEXT]\n${this.ocrPrompt}\n\n` : '';
        const contextSection = contextText.trim() ? `[RETRIEVED MEMORY]\n${contextText}\n\n` : '';
        const instructionsSection = `[INSTRUCTIONS]\n${this.systemPrompt}\n\n`;
        const systemPromptWithContext = visionSection + ocrSection + contextSection + instructionsSection;

        const response = await apiFetch('/api/completion', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: lastUserMessage.content,
                history: historyUpToMessage.slice(0, -1),
                systemPrompt: systemPromptWithContext
            })
        });

        if (!response.ok) {
            console.error("Error during regeneration");
            return;
        }

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        if (!reader) return;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            this.messages[index].content += chunk;
            this.notifySubscribers('onMessagesChange');
        }
        
        await updateSession(this.sessionId, this.messages);
        this.notifySubscribers('onMessagesChange');
    }

    public getMessages(): HistoryItem[] {
        return this.messages;
    }

    public setMessages(messages: HistoryItem[]) {
        this.messages = messages;
        this.notifySubscribers('onMessagesChange');
    }

    public getSessionId(): string | null {
        return this.sessionId;
    }

    public async setSessionId(id: string | null) {
        this.sessionId = id;
        if (id) {
            const session = await fetchSessionContent(id);
            this.messages = session ? (session.history || []) : [];
        } else {
            this.messages = [];
        }
        this.notifySubscribers('onMessagesChange');
    }
}

export const chatManager = new ChatManager();
