import { useState, useEffect } from "react"
import { SidebarProvider } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"
import pageMapping from "@/constants/page-mapping"
import { globalStateManager } from "@/lib/globalStateManager"
import { chatManager } from "@/lib/chatManager"

type PageKey = keyof typeof pageMapping

function Mainpage() {
    const [currentPage, setCurrentPage] = useState<PageKey>("llm")
    const [systemState, setSystemState] = useState<string>("IDLE")
    const inputMode = "wake_word"
    const [lastCommand, setLastCommand] = useState<string>("")
    const [lastResponse, setLastResponse] = useState<string>("")

    useEffect(() => {
        const unsubLLM = globalStateManager.subscribe('isLLMThinking', (thinking) => {
            if (thinking) setSystemState("THINKING");
            else if (!globalStateManager.getState('isTTSPlaying')) setSystemState("IDLE");
        });
        const unsubTTS = globalStateManager.subscribe('isTTSPlaying', (playing) => {
            if (playing) setSystemState("SPEAKING");
            else if (!globalStateManager.getState('isLLMThinking')) setSystemState("IDLE");
        });
        const unsubRec = globalStateManager.subscribe('isVoiceRecording', (rec) => {
            if (rec && !globalStateManager.getState('isTTSPlaying') && !globalStateManager.getState('isLLMThinking')) {
                setSystemState("LISTENING");
            }
        });
        const unsubChat = chatManager.subscribe((messages) => {
            if (messages && messages.length > 0) {
                const userMsgs = messages.filter((m) => m.role === 'user');
                const asstMsgs = messages.filter((m) => m.role === 'assistant');
                if (userMsgs.length > 0) setLastCommand(userMsgs[userMsgs.length - 1].content || "");
                if (asstMsgs.length > 0) setLastResponse(asstMsgs[asstMsgs.length - 1].content || "");
            }
        });

        return () => {
            unsubLLM();
            unsubTTS();
            unsubRec();
            unsubChat();
        };
    }, []);

    return (
        <SidebarProvider open={false}>
            <AppSidebar onItemClick={setCurrentPage} activePage={currentPage} />
            <div className="flex flex-col w-full h-screen">
                {/* Demo status bar - pinned outside scroll area */}
                <header className="shrink-0 h-9 bg-muted/40 border-b px-4 flex items-center justify-between text-xs text-muted-foreground z-20 select-none">
                    <div className="flex items-center space-x-3 shrink-0">
                        <span className="font-semibold text-foreground tracking-wide">KYOMA Status:</span>
                        <span className="inline-flex items-center gap-1.5">
                            <span className={`h-2 w-2 rounded-full ${
                                systemState === "LISTENING" ? "bg-green-500 animate-pulse" :
                                systemState === "THINKING" ? "bg-amber-500 animate-pulse" :
                                systemState === "SPEAKING" ? "bg-blue-500 animate-pulse" : "bg-gray-400"
                            }`} />
                            <strong className="text-foreground font-mono">{systemState}</strong>
                        </span>
                        <span className="hidden sm:inline">Mode: <span className="font-mono text-foreground font-semibold">{inputMode}</span></span>
                    </div>
                    {(lastCommand || lastResponse) && (
                        <div 
                            className="truncate max-w-md md:max-w-xl text-right text-xs" 
                            title={`${lastCommand ? `Command: ${lastCommand}` : ''}${lastResponse ? `
Response: ${lastResponse}` : ''}`}
                        >
                            {lastCommand && <span className="mr-2 opacity-80">Last: &ldquo;{lastCommand}&rdquo;</span>}
                            {lastResponse && <span className="text-foreground font-medium">&rarr; &ldquo;{lastResponse.length > 40 ? lastResponse.slice(0, 40) + '...' : lastResponse}&rdquo;</span>}
                        </div>
                    )}
                </header>
                <main className="flex-1 relative">
                    {Object.entries(pageMapping).map(([key, { page: PageComponent }]) => {
                        const isActive = currentPage === key;
                        const unmount = key === "memory";

                        // Special handling for character page - minimize instead of unmount
                        if (!unmount) {
                            return (
                                <div
                                    key={key}
                                    style={{
                                        width: isActive ? "100%" : "1px",
                                        height: isActive ? "100%" : "1px",
                                        position: "absolute",
                                        overflow: isActive ? "visible" : "hidden",
                                        pointerEvents: isActive ? "auto" : "none",
                                    }}
                                >
                                    <PageComponent isActive={isActive} />
                                </div>
                            );
                        }

                        // Normal handling for other pages - mount/unmount
                        return isActive ? (
                            <div key={key} className="absolute w-full h-full">
                                <PageComponent isActive={true} />
                            </div>
                        ) : null;
                    })}
                </main>
            </div>
        </SidebarProvider>
    );
}

export default Mainpage;