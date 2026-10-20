import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Send, Square, Plus, MoreHorizontal, Edit, Trash2, Mic, MicOff } from 'lucide-react';
import { useSettings } from '@/context/SettingsContext';
import EditableChatHistory from './editable-chat-history';
import { HistoryItem } from '@/lib/types';
import { chatManager } from '@/lib/chatManager';
import { fetchSessions, createNewSession, deleteSession, updateSessionTitle } from '@/lib/sessionManager';
import { Session } from '@/lib/types';
import { SidePanel } from './side-panel';
import { SidebarMenuButton } from './ui/sidebar';
import { apiFetch } from '@/lib/api-client';
import { globalStateManager } from '@/lib/globalStateManager';
import { pipelineManager } from '@/lib/pipelineManager';
import { ttsManager } from '@/lib/ttsManager';

import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

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
    }, [isTTSPlaying]);


    const initSessionOnLoad = async () => {
        const data = await fetchSessions();
        setSessionList(data);
        
        // Auto-create 'Chat #N' on fresh app launch
        const chatNum = (data?.length || 0) + 1;
        const autoTitle = `Chat #${chatNum}`;
        const newSessionId = await createNewSession(autoTitle);
        if (newSessionId) {
            const updated = await fetchSessions();
            setSessionList(updated);
            setSelectedSession(newSessionId);
            window.__kyoma_sessions_cache = updated;
        } else if (data.length > 0) {
            setSelectedSession(data[0].id);
        }
    };

    const getSessions = async () => {
        const data = await fetchSessions();
        setSessionList(data);
        if (data.length > 0 && !selectedSession) {
            setSelectedSession(data[0].id);
        } else if (data.length === 0 && selectedSession) {
            setSelectedSession(null);
        }
    };

    const handleCreateNewSession = async () => {
        const chatNum = (sessionList?.length || 0) + 1;
        const newSessionId = await createNewSession(`Chat #${chatNum}`);
        if (newSessionId) {
            await getSessions();
            setSelectedSession(newSessionId);
        }
    };

    const handleDeleteSession = async (sessionId: string) => {
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

    // Check if current session has messages
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

    const handleSend = async (input: string) => {
        if (input.trim() === '') return;
        
        // Auto-rename session to topic preview if it's currently a default or numbered chat
        if (selectedSession) {
            const currentSession = sessionList.find(s => s.id === selectedSession);
            if (currentSession && (/^Chat #\d+$/.test(currentSession.title) || currentSession.title === 'New Chat')) {
                const topic = input.trim().replace(/[\r\n]+/g, ' ');
                const preview = topic.length > 28 ? topic.slice(0, 28).trim() + '...' : topic;
                handleRenameSession(selectedSession, preview);
            }
        }

        setIsProcessing(true);
        setInput('');
        await chatManager.sendMessage(input);
        setIsProcessing(false);
        inputRef.current?.focus(); // Focus after sending
    };

    useEffect(() => {
        if (!isProcessing) {
            inputRef.current?.focus(); // Focus when processing completes
        }
    }, [isProcessing]);

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
            <div className="sticky bottom-0 bg-background rounded-t-lg">
                <div className='mb-4 flex w-full items-center space-x-2 bg-secondary rounded-lg px-4 py-6'>
                    <Input
                        ref={inputRef}
                        disabled={isProcessing}
                        value={input}
                        placeholder="Type your message here."
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
                    {isTTSPlaying && (
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
                        {!isProcessing ? <Send></Send> : <Square></Square>}
                    </Button>
                </div>
            </div>

        </div>
    );
};

export default Chatbox;