import { useState, useEffect } from "react"
import { Edit3, Save, X, Trash, ArrowRight, RotateCcw } from "lucide-react"
import { Button } from "./ui/button"
import { Textarea } from "./ui/textarea"
import { HistoryItem } from "@/lib/types"
import { TooltipContent, TooltipTrigger } from "./ui/tooltip"
import { Tooltip } from "./ui/tooltip"
import { TooltipProvider } from "./ui/tooltip"
import { toast } from "sonner"
import { apiFetch } from "@/lib/api-client"
import { globalStateManager } from "@/lib/globalStateManager"

interface EditableChatHistoryProps {
    messages: HistoryItem[]
    sessionId: string
    onUpdate: (updatedHistory: HistoryItem[]) => void
    onContinue: (index: number) => void
    onRegenerate: (index: number) => void
}

/**
 * Animated thinking bubble showing progress dots, subtle shimmer,
 * and dynamic stage text ("Searching...", "Reading sources...", "Preparing answer...").
 */
function ThinkingBubble({ stage }: { stage: string }) {
    return (
        <div className="flex flex-col gap-1.5 self-start">
            <div className="text-xs text-muted-foreground self-start">
                AI
            </div>
            <div className="break-words max-w-7/10 w-fit px-4 py-2.5 rounded-lg text-sm font-medium shadow-xs bg-secondary text-secondary-foreground border border-border/50 animate-pulse transition-all">
                <div className="flex items-center space-x-2.5">
                    {/* 3 Bouncing Dots */}
                    <div className="flex items-center space-x-1">
                        <span className="w-2 h-2 rounded-full bg-primary/70 animate-bounce [animation-delay:-0.3s]" />
                        <span className="w-2 h-2 rounded-full bg-primary/70 animate-bounce [animation-delay:-0.15s]" />
                        <span className="w-2 h-2 rounded-full bg-primary/70 animate-bounce" />
                    </div>
                    {/* Stage description */}
                    <span className="text-xs text-muted-foreground font-medium tracking-wide">
                        {stage || "Thinking..."}
                    </span>
                </div>
            </div>
        </div>
    );
}

export default function EditableChatHistory({ messages, sessionId, onUpdate, onContinue, onRegenerate }: EditableChatHistoryProps) {
    const [editingMessageIndex, setEditingMessageIndex] = useState<number | null>(null)
    const [editContent, setEditContent] = useState("")
    const [isThinking, setIsThinking] = useState(false)
    const [thinkingStage, setThinkingStage] = useState("Preparing answer...")

    useEffect(() => {
        const unsub = globalStateManager.subscribe('isLLMThinking', (thinking) => {
            setIsThinking(thinking);
            if (thinking) {
                setThinkingStage("Preparing answer...");
            }
        });
        setIsThinking(globalStateManager.getState('isLLMThinking'));
        return () => unsub();
    }, []);

    const startEditing = (index: number) => {
        setEditingMessageIndex(index)
        setEditContent(messages[index].content)
    }

    const continueMessage = (index: number) => {
        onContinue(index)
    }

    const regenerateMessage = (index: number) => {
        onRegenerate(index)
    }

    const deleteMessage = async (index: number) => {
        try {
            const updatedHistory = [...messages]
            updatedHistory.splice(index, 1)

            const response = await apiFetch(`/api/chat/session/update`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: sessionId,
                    history: updatedHistory
                }),
            })

            if (!response.ok) {
                throw new Error('Failed to update message')
            }

            onUpdate(updatedHistory)
        } catch (err) {
            toast.error(err instanceof Error ? err.message : 'Failed to update message')
        }
    }

    const saveEdit = async () => {
        if (editingMessageIndex === null) return

        try {
            const updatedHistory = [...messages]
            updatedHistory[editingMessageIndex] = {
                ...updatedHistory[editingMessageIndex],
                content: editContent
            }

            const response = await apiFetch(`/api/chat/session/update`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: sessionId,
                    history: updatedHistory
                }),
            })

            if (!response.ok) {
                throw new Error('Failed to update message')
            }

            onUpdate(updatedHistory)
            setEditingMessageIndex(null)
            setEditContent("")
        } catch (err) {
            toast.error(err instanceof Error ? err.message : 'Failed to update message')
        }
    }

    const cancelEdit = () => {
        setEditingMessageIndex(null)
        setEditContent("")
    }

    // Filter out empty assistant placeholder from messages list so we render ThinkingBubble cleanly instead
    const renderedMessages = messages.filter((m) => {
        if (m.role === 'assistant' && (!m.content || m.content.trim() === '')) {
            // Keep empty only if not thinking (e.g. streaming just about to start with first token)
            return false;
        }
        return true;
    });

    const lastMessage = messages.length > 0 ? messages[messages.length - 1] : null;
    const isLastAssistantEmpty = lastMessage?.role === 'assistant' && (!lastMessage.content || lastMessage.content.trim() === '');
    // Once actual answer content exists, Preparing answer must disappear. No stale THINKING state after completion.
    const showThinkingBubble = isThinking && (messages.length === 0 || lastMessage?.role === 'user' || isLastAssistantEmpty);

    return (
        <div className="flex flex-col space-y-4">
            {renderedMessages.map((message, index) => (
                <div key={index} className="group relative flex flex-col gap-1.5">
                    <div className={`text-xs text-muted-foreground ${message.role === 'user'
                        ? 'self-end'
                        : 'self-start'
                    }`}>
                        {message.role === 'user' ? 'You' : 'AI'}
                    </div>
                    <div
                        className={`break-words max-w-7/10 w-fit px-4 py-2 rounded-md text-sm font-medium shadow-xs bg-secondary text-secondary-foreground
                             ${message.role === 'user'
                                ? 'self-end'
                                : 'self-start'
                            }`}
                    >
                        {editingMessageIndex === index ? (
                            <div className="space-y-3">
                                <Textarea
                                    value={editContent}
                                    onChange={(e) => setEditContent(e.target.value)}
                                    className="min-h-24"
                                />
                                <div className="flex space-x-2">
                                    <Button size="sm" onClick={saveEdit}>
                                        <Save className="h-4 w-4 mr-2" />
                                        Save
                                    </Button>
                                    <Button size="sm" variant="outline" onClick={cancelEdit}>
                                        <X className="h-4 w-4 mr-2" />
                                        Cancel
                                    </Button>
                                </div>
                            </div>
                        ) : (
                            <div className={`whitespace-pre-wrap ${message.role === 'user'
                                ? 'opacity-80'
                                : 'opacity-100'
                            }`}>{message.content}</div>
                        )}
                    </div>
                    {editingMessageIndex !== index && (
                        <div className={`opacity-0 group-hover:opacity-100 transition-opacity ${message.role === 'user'
                                ? 'self-end ml-auto'
                                : 'self-start mr-auto'
                            }`}>
                            <TooltipProvider>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <Button variant="ghost" size="sm" onClick={() => continueMessage(index)}>
                                            <ArrowRight className="h-4 w-4" />
                                        </Button>
                                    </TooltipTrigger>
                                    <TooltipContent side="bottom" sideOffset={14}>
                                        Continue Message
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider>
                            {message.role === 'assistant' && (
                                <TooltipProvider>
                                    <Tooltip>
                                        <TooltipTrigger asChild>
                                            <Button variant="ghost" size="sm" onClick={() => regenerateMessage(index)}>
                                                <RotateCcw className="h-4 w-4" />
                                            </Button>
                                        </TooltipTrigger>
                                        <TooltipContent side="bottom" sideOffset={14}>
                                            Regenerate Message
                                        </TooltipContent>
                                    </Tooltip>
                                </TooltipProvider>
                            )}
                            <TooltipProvider>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <Button variant="ghost" size="sm" onClick={() => startEditing(index)}>
                                            <Edit3 className="h-4 w-4" />
                                        </Button>
                                    </TooltipTrigger>
                                    <TooltipContent side="bottom" sideOffset={14}>
                                        Edit Message
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider>
                            <TooltipProvider>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <Button variant="ghost" size="sm" onClick={() => deleteMessage(index)}>
                                            <Trash className="h-4 w-4" />
                                        </Button>
                                    </TooltipTrigger>
                                    <TooltipContent side="bottom" sideOffset={14}>
                                        Delete Message
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider>
                        </div>
                    )}
                </div>
            ))}
            {/* Show polished animated thinking bubble without empty pill or layout jump */}
            {showThinkingBubble && (
                <ThinkingBubble stage={thinkingStage} />
            )}
        </div>
    )
}
