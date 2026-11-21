import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Send, Square, Plus, MoreHorizontal, Edit, Trash2, Mic, MicOff, Play, X, Check } from 'lucide-react';
import { useSettings } from '@/context/SettingsContext';
import EditableChatHistory from './editable-chat-history';
import { HistoryItem } from '@/lib/types';
import { chatManager } from '@/lib/chatManager';
import { fetchSessions, createNewSession, deleteSession, updateSessionTitle } from '@/lib/sessionManager';
import { Session } from '@/lib/types';
import { SidePanel } from './side-panel';
import { SidebarMenuButton } from './ui/sidebar';

import { globalStateManager } from '@/lib/globalStateManager';
import { pipelineManager } from '@/lib/pipelineManager';
import { stopAll } from '@/lib/stopController';

import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface QueuedMessage {
    id: string;
    text: string;
}

const Chatbox = () => {
    const [displayedMessages, setDisplayedMessages] = useState<HistoryItem[]>([]);
    const [input, setInput] = useState('');
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const [isProcessing, setIsProcessing] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);
    const { settings } = useSettings();
    const [sessionList, setSessionList] = useState<Session[]>([]);
    const [selectedSession, setSelectedSession] = useState<string | null>(null);
    const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
    const [editingTitle, setEditingTitle] = useState<string>('');
    const [isTTSPlaying, setIsTTSPlaying] = useState<boolean>(false);
    const [isLLMThinking, setIsLLMThinking] = useState<boolean>(false);
    const [isVoiceRecording, setIsVoiceRecording] = useState<boolean>(false);
    const [hasActiveTask, setHasActiveTask] = useState<boolean>(false);

    // FIFO Message Queue (up to 5 queued items)
    const [messageQueue, setMessageQueue] = useState<QueuedMessage[]>([]);
    const [isQueuePaused, setIsQueuePaused] = useState<boolean>(false);
    const [editingQueueId, setEditingQueueId] = useState<string | null>(null);
    const [editingQueueText, setEditingQueueText] = useState<string>('');
    const messageQueueRef = useRef<QueuedMessage[]>([]);
    messageQueueRef.current = messageQueue;
    const isQueuePausedRef = useRef<boolean>(false);
    isQueuePausedRef.current = isQueuePaused;

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
        stopAll().catch(() => {});
        setHasActiveTask(false);
        setIsProcessing(false);
        // Stop pauses the queue and exposes Resume/Clear
        setIsQueuePaused(true);
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
    }, [isTurnActive]);

    const initRunningRef = useRef(false);

    const initSessionOnLoad = async () => {
        if (initRunningRef.current) return;
        initRunningRef.current = true;
        try {
            const data = await fetchSessions(true);
            setSessionList(data);
            
            const launchSessionId = sessionStorage.getItem("kyoma_launch_session_id");
            if (launchSessionId && data.some((s: Session) => s.id === launchSessionId)) {
                setSelectedSession(launchSessionId);
                return;
            }

            const latestSession = data && data.length > 0 ? data[0] : null;
            if (latestSession && (!latestSession.history || latestSession.history.length === 0)) {
                setSelectedSession(latestSession.id);
                sessionStorage.setItem("kyoma_launch_session_id", latestSession.id);
            } else {
                const newSessionId = await createNewSession();
                if (newSessionId) {
                    const updated = await fetchSessions(true);
                    setSessionList(updated);
                    setSelectedSession(newSessionId);
                    sessionStorage.setItem("kyoma_launch_session_id", newSessionId);
                    window.__kyoma_sessions_cache = updated;
                }
            }
        } finally {
            initRunningRef.current = false;
        }
    };

    const getSessions = async () => {
        const data = await fetchSessions(true);
        setSessionList(data);
        if (data.length > 0 && !selectedSession) {
            setSelectedSession(data[0].id);
        } else if (data.length === 0 && selectedSession) {
            setSelectedSession(null);
        }
    };

    const handleCreateNewSession = async () => {
        if (selectedSession) {
            const current = sessionList.find((s: Session) => s.id === selectedSession);
            if (current && (!current.history || current.history.length === 0) && displayedMessages.length === 0) {
                return;
            }
        }
        const newSessionId = await createNewSession();
        if (newSessionId) {
            await getSessions();
            setSelectedSession(newSessionId);
            sessionStorage.setItem("kyoma_launch_session_id", newSessionId);
        }
    };

    const handleDeleteSession = async (sessionId: string) => {
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
                createNewSession().then(newId => {
                    if (newId) {
                        setSelectedSession(newId);
                        sessionStorage.setItem("kyoma_launch_session_id", newId);
                        getSessions();
                    } else {
                        setSelectedSession(null);
                        chatManager.setSessionId(null);
                        setDisplayedMessages([]);
                    }
                }).catch(() => {
                    setSelectedSession(null);
                    chatManager.setSessionId(null);
                    setDisplayedMessages([]);
                });
            }
        }
    };

    const handleRenameSession = async (sessionId: string, newTitle: string) => {
        const success = await updateSessionTitle(sessionId, newTitle);
        if (success) {
            await getSessions();
            setEditingSessionId(null);
            setEditingTitle('');
        }
    };

    const startEditing = (session: Session) => {
        setEditingSessionId(session.id);
        setEditingTitle(session.title);
    };

    const cancelEditing = () => {
        setEditingSessionId(null);
        setEditingTitle('');
    };

    const saveEditing = async () => {
        if (editingSessionId && editingTitle.trim()) {
            await handleRenameSession(editingSessionId, editingTitle.trim());
        }
    };

    const isCurrentSessionEmpty = displayedMessages.length === 0;

    useEffect(() => {
        initSessionOnLoad();
    }, []);

    useEffect(() => {
        if (selectedSession) {
            chatManager.setSessionId(selectedSession);
        }
    }, [selectedSession]);

    useEffect(() => {
        chatManager.setSystemPrompt(settings["llm.system_prompt"]);
    }, [settings["llm.system_prompt"]]);

    useEffect(() => {
        chatManager.setEnableMemoryRetrieval(settings["llm.enableMemoryRetrieval"] ?? true);
    }, [settings["llm.enableMemoryRetrieval"]]);

    useEffect(() => {
        const unsubscribe = chatManager.subscribe((messages) => {
            if (displayedMessages !== messages) {
                setDisplayedMessages(messages);
            }
        }, { onMessagesChange: true });

        return () => unsubscribe();
    }, []);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [displayedMessages]);

    // Dispatch the next message only after the previous answer's audio has completely finished
    useEffect(() => {
        if (isTurnActive || isProcessing || isQueuePaused) return;
        if (messageQueue.length === 0) return;

        const nextItem = messageQueue[0];
        setMessageQueue(prev => prev.slice(1));
        dispatchMessage(nextItem.text);
    }, [isTurnActive, isProcessing, isQueuePaused, messageQueue]);

    const dispatchMessage = async (msgText: string) => {
        if (selectedSession) {
            const currentSession = sessionList.find(s => s.id === selectedSession);
            if (currentSession && (currentSession.title === 'New Session' || currentSession.title === 'New Chat' || /^Chat #\d+$/.test(currentSession.title))) {
                const topic = msgText.trim().replace(/[\r\n]+/g, ' ');
                const preview = topic.length > 28 ? topic.slice(0, 28).trim() + '...' : topic;
                handleRenameSession(selectedSession, preview);
            }
        }

        setIsProcessing(true);
        try {
            await chatManager.sendMessage(msgText);
        } finally {
            setIsProcessing(false);
            inputRef.current?.focus();
        }
    };

    const handleSend = (textToSend: string) => {
        const trimmed = textToSend.trim();
        if (!trimmed) return;
        setInput('');

        // If turn or processing is active, enqueue into FIFO queue (maximum 5)
        if (isTurnActive || isProcessing) {
            if (messageQueue.length < 5) {
                const newItem: QueuedMessage = {
                    id: `${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    text: trimmed,
                };
                setMessageQueue(prev => [...prev, newItem]);
            }
            return;
        }

        dispatchMessage(trimmed);
    };

    const handleRemoveQueueItem = (id: string) => {
        setMessageQueue(prev => prev.filter(item => item.id !== id));
    };

    const handleStartEditQueue = (item: QueuedMessage) => {
        setEditingQueueId(item.id);
        setEditingQueueText(item.text);
    };

    const handleSaveEditQueue = () => {
        if (editingQueueId && editingQueueText.trim()) {
            setMessageQueue(prev => prev.map(item => item.id === editingQueueId ? { ...item, text: editingQueueText.trim() } : item));
        }
        setEditingQueueId(null);
        setEditingQueueText('');
    };

    return (
        <div className="flex flex-col max-w-3xl mx-auto h-[calc(100vh-50px-17px)]">
            <SidePanel side="left" isOpen={false}>
                <div className="w-full mb-4">
                    <Button 
                        onClick={handleCreateNewSession}
                        disabled={isProcessing || isCurrentSessionEmpty}
                        className="w-full flex items-center gap-2"
                        variant="outline"
                    >
                        <Plus className="h-4 w-4" />
                        New Session
                    </Button>
                </div>
                {sessionList.map((session) => (
                    <div key={session.id} className="relative group w-full">
                        {editingSessionId === session.id ? (
                            <div className="flex items-center gap-2 p-2">
                                <Input
                                    value={editingTitle}
                                    onChange={(e) => setEditingTitle(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') {
                                            saveEditing();
                                        } else if (e.key === 'Escape') {
                                            cancelEditing();
                                        }
                                    }}
                                    onBlur={saveEditing}
                                    className="flex-1 text-sm"
                                    autoFocus
                                />
                            </div>
                        ) : (
                            <SidebarMenuButton 
                                disabled={isProcessing} 
                                className={`${selectedSession === session.id ? 'bg-muted' : ''} w-full`}
                                onClick={() => setSelectedSession(session.id)}
                            >
                                <div className='flex flex-row justify-between items-center w-full'> 
                                    <span className="truncate">{session.title}</span>
                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <div
                                                className="h-6 w-6 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                                                onClick={(e) => e.stopPropagation()}
                                            >
                                                <MoreHorizontal className="h-4 w-4" />
                                            </div>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end">
                                            <DropdownMenuItem onClick={() => startEditing(session)}>
                                                <Edit className="h-4 w-4 mr-2" />
                                                Rename
                                            </DropdownMenuItem>
                                            <DropdownMenuItem 
                                                onClick={() => handleDeleteSession(session.id)}
                                                className="text-destructive"
                                            >
                                                <Trash2 className="h-4 w-4 mr-2" />
                                                Delete
                                            </DropdownMenuItem>
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </div>
                            </SidebarMenuButton>
                        )}
                    </div>
                ))}
            </SidePanel>
            <div className="flex flex-col space-y-4 mb-4 flex-grow">
                <EditableChatHistory
                    messages={displayedMessages}
                    sessionId={chatManager.getSessionId() ?? ""}
                    onUpdate={(history) => {
                        chatManager.setMessages(history);
                    }}
                    onContinue={(index) => {
                        chatManager.continueMessage(index);
                    }}
                    onRegenerate={(index) => {
                        chatManager.regenerateMessage(index);
                    }}
                />
                <div ref={messagesEndRef}></div>
            </div>

            {/* FIFO Queue Container with Up Next, Edit, Cancel, Resume & Clear */}
            {messageQueue.length > 0 && (
                <div className="mb-2 p-2.5 bg-secondary/70 border border-border/70 rounded-lg text-xs space-y-1.5 shadow-xs">
                    <div className="flex items-center justify-between font-semibold text-muted-foreground pb-1 border-b border-border/40">
                        <span className="flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-primary/80 animate-pulse"></span>
                            Up next ({messageQueue.length}/5)
                            {isQueuePaused && <span className="text-yellow-500 font-bold ml-1">(Paused)</span>}
                        </span>
                        <div className="flex items-center gap-1">
                            {isQueuePaused ? (
                                <Button size="sm" variant="outline" className="h-5 px-2 text-[10px]" onClick={() => setIsQueuePaused(false)}>
                                    <Play className="h-3 w-3 mr-1" /> Resume
                                </Button>
                            ) : null}
                            <Button size="sm" variant="ghost" className="h-5 px-2 text-[10px] text-destructive hover:text-destructive" onClick={() => setMessageQueue([])}>
                                Clear
                            </Button>
                        </div>
                    </div>
                    <div className="space-y-1 max-h-28 overflow-y-auto pr-1">
                        {messageQueue.map((item, qIdx) => (
                            <div key={item.id} className="flex items-center justify-between gap-2 p-1.5 rounded bg-background/50 border border-border/30">
                                {editingQueueId === item.id ? (
                                    <div className="flex items-center gap-1 w-full">
                                        <Input
                                            value={editingQueueText}
                                            onChange={(e) => setEditingQueueText(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter') handleSaveEditQueue();
                                                if (e.key === 'Escape') setEditingQueueId(null);
                                            }}
                                            className="h-6 text-xs flex-1"
                                            autoFocus
                                        />
                                        <Button size="icon" variant="ghost" className="h-6 w-6 text-green-500" onClick={handleSaveEditQueue}>
                                            <Check className="h-3.5 w-3.5" />
                                        </Button>
                                        <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditingQueueId(null)}>
                                            <X className="h-3.5 w-3.5" />
                                        </Button>
                                    </div>
                                ) : (
                                    <>
                                        <span className="truncate flex-1 text-foreground">
                                            <span className="text-muted-foreground mr-1.5">{qIdx + 1}.</span>
                                            {item.text}
                                        </span>
                                        <div className="flex items-center gap-0.5 shrink-0">
                                            <Button size="icon" variant="ghost" className="h-5 w-5" onClick={() => handleStartEditQueue(item)} title="Edit queued message">
                                                <Edit className="h-3 w-3 text-muted-foreground" />
                                            </Button>
                                            <Button size="icon" variant="ghost" className="h-5 w-5 hover:text-destructive" onClick={() => handleRemoveQueueItem(item.id)} title="Cancel queued message">
                                                <X className="h-3 w-3" />
                                            </Button>
                                        </div>
                                    </>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <div className="sticky bottom-0 bg-background rounded-t-lg">
                <div className='mb-4 flex w-full items-center space-x-2 bg-secondary rounded-lg px-4 py-6'>
                    {/* Input remains enabled while Kyoma thinks or speaks */}
                    <Input
                        ref={inputRef}
                        disabled={false}
                        value={input}
                        placeholder={isTurnActive ? "Kyoma is responding... type and send to queue" : "Type your message here."}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && handleSend(input)}
                    />
                    <Button
                        type="button"
                        variant={isVoiceRecording ? "destructive" : "outline"}
                        size="icon"
                        title={isVoiceRecording ? "Mute / Stop Voice Recording" : "Start Voice Recording"}
                        onClick={() => {
                            globalStateManager.updateState('isVoiceRecording', !isVoiceRecording);
                        }}
                    >
                        {isVoiceRecording ? <Mic className="h-5 w-5 text-red-500 animate-pulse" /> : <MicOff className="h-5 w-5" />}
                    </Button>
                    {isTurnActive && (
                        <Button
                            variant="destructive"
                            size="icon"
                            title="Stop Speaking / Interrupt (or press .)"
                            onClick={handleStopAndReset}
                        >
                            <Square />
                        </Button>
                    )}
                    <Button onClick={() => handleSend(input)}>
                        <Send className="h-4 w-4" />
                    </Button>
                </div>
            </div>

        </div>
    );
};

export default Chatbox;
