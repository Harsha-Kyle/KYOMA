path = r'LocalAIVtuber2-master\frontend\src\components\chatbox.tsx'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

old_block = '''    const [isTTSPlaying, setIsTTSPlaying] = useState<boolean>(false);
    const [isVoiceRecording, setIsVoiceRecording] = useState<boolean>(false);

    useEffect(() => {
        const unsubTTS = globalStateManager.subscribe('isTTSPlaying', (playing) => {
            setIsTTSPlaying(playing);
        });
        const unsubVoice = globalStateManager.subscribe('isVoiceRecording', (rec) => {
            setIsVoiceRecording(rec);
        });
        setIsTTSPlaying(globalStateManager.getState('isTTSPlaying'));
        setIsVoiceRecording(globalStateManager.getState('isVoiceRecording'));
        return () => {
            unsubTTS();
            unsubVoice();
        };
    }, []);

    const handleStopAndReset = () => {
        ttsManager.stopAllAudio();
        chatManager.stopGeneration();
        pipelineManager.cancelAllTasks();
        pipelineManager.interruptCurrentTask();
        apiFetch('/api/record/unmute', { method: 'POST' }).catch(() => {});
        globalStateManager.updateState('isTTSPlaying', false);
        globalStateManager.updateState('isLLMThinking', false);
    };

    useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key !== '.') return;
            const tag = (document.activeElement as HTMLElement)?.tagName?.toLowerCase();
            if (tag === 'input' || tag === 'textarea') return;
            if (isTTSPlaying || globalStateManager.getState('isLLMThinking')) {
                handleStopAndReset();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isTTSPlaying]);'''

new_block = '''    const [isTTSPlaying, setIsTTSPlaying] = useState<boolean>(false);
    const [isLLMThinking, setIsLLMThinking] = useState<boolean>(false);
    const [isVoiceRecording, setIsVoiceRecording] = useState<boolean>(false);
    const [hasActiveTask, setHasActiveTask] = useState<boolean>(false);

    useEffect(() => {
        const updateTaskState = () => {
            const task = pipelineManager.getCurrentTask();
            setHasActiveTask(!!task && task.status !== 'task_finished' && task.status !== 'cancelled');
        };

        const unsubTTS = globalStateManager.subscribe('isTTSPlaying', (playing) => {
            setIsTTSPlaying(playing);
            updateTaskState();
        });
        const unsubLLM = globalStateManager.subscribe('isLLMThinking', (thinking) => {
            setIsLLMThinking(thinking);
            updateTaskState();
        });
        const unsubVoice = globalStateManager.subscribe('isVoiceRecording', (rec) => {
            setIsVoiceRecording(rec);
        });
        const unsubPipeline = pipelineManager.subscribe(updateTaskState);

        setIsTTSPlaying(globalStateManager.getState('isTTSPlaying'));
        setIsLLMThinking(globalStateManager.getState('isLLMThinking'));
        setIsVoiceRecording(globalStateManager.getState('isVoiceRecording'));
        updateTaskState();

        return () => {
            unsubTTS();
            unsubLLM();
            unsubVoice();
            unsubPipeline();
        };
    }, []);

    const isTurnActive = isTTSPlaying || isLLMThinking || hasActiveTask;

    const handleStopAndReset = () => {
        ttsManager.stopAllAudio();
        chatManager.stopGeneration();
        pipelineManager.cancelAllTasks();
        pipelineManager.interruptCurrentTask();
        apiFetch('/api/record/unmute', { method: 'POST' }).catch(() => {});
        globalStateManager.updateState('isTTSPlaying', false);
        globalStateManager.updateState('isLLMThinking', false);
        setHasActiveTask(false);
    };

    useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key !== '.') return;
            const tag = (document.activeElement as HTMLElement)?.tagName?.toLowerCase();
            if (tag === 'input' || tag === 'textarea') return;
            if (isTurnActive) {
                handleStopAndReset();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isTurnActive]);'''

assert old_block in text, 'old_block not found!'
text = text.replace(old_block, new_block, 1)

old_delete = '''    const handleDeleteSession = async (sessionId: string) => {
        await deleteSession(sessionId);
        await getSessions(); // Refresh the session list
        if (selectedSession === sessionId) {
            const remainingSessions = sessionList.filter(s => s.id !== sessionId);
            if (remainingSessions.length > 0) {
                setSelectedSession(remainingSessions[0].id);
            } else {
                setSelectedSession(null);
            }
        }
    };'''

new_delete = '''    const handleDeleteSession = async (sessionId: string) => {
        try {
            await deleteSession(sessionId);
        } catch (err) {
            console.error('Failed to delete session on backend:', err);
        }
        const remaining = sessionList.filter(s => s.id !== sessionId);
        setSessionList(remaining);
        if (selectedSession === sessionId) {
            if (remaining.length > 0) {
                setSelectedSession(remaining[0].id);
            } else {
                setSelectedSession(null);
                chatManager.setSessionId(null);
                setDisplayedMessages([]);
            }
        }
    };'''

assert old_delete in text, 'old_delete not found!'
text = text.replace(old_delete, new_delete, 1)

old_btn = '''                    {isTTSPlaying && (
                        <Button
                            variant="destructive"
                            size="icon"
                            title="Stop Speaking / Interrupt (or press .)"
                            onClick={handleStopAndReset}
                        >
                            <Square />
                        </Button>
                    )}'''

new_btn = '''                    {isTurnActive && (
                        <Button
                            variant="destructive"
                            size="icon"
                            title="Stop Speaking / Interrupt (or press .)"
                            onClick={handleStopAndReset}
                        >
                            <Square />
                        </Button>
                    )}'''

assert old_btn in text, 'old_btn not found!'
text = text.replace(old_btn, new_btn, 1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print('Successfully updated chatbox.tsx')
