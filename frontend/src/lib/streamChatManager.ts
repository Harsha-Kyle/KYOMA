import { apiFetch, getApiKey } from "./api-client";

export class StreamChatManager {
    private socket: WebSocket | null = null;
    private isFetching: boolean = false;

    constructor(private onMessage: (message: string) => void) {}

    async startChatFetch(): Promise<void> {
        try {
            const response = await apiFetch("/api/streamChat/yt/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
            });

            if (response.ok) {
                const key = getApiKey();
                const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
                const wsUrl = `${wsProtocol}://${window.location.host}/ws/streamChat${key ? `?api_key=${encodeURIComponent(key)}` : ""}`;
                this.socket = new WebSocket(wsUrl);
                this.isFetching = true;



                this.socket.onmessage = (event) => {
                    const message = JSON.parse(event.data);
                    this.onMessage(`You are hosting a karaoke stream today where the plan is to sing and chat with viewers. You are looking through Stream chat, repeat the viewer's message and commentate on them.
                        Here is a viewer's message ${message.author} said: ${message.message}`);
                };

                this.socket.onerror = (error) => console.error("WebSocket error:", error);
            } else {
                const errorData = await response.json();
                console.error(`Error: ${errorData.error}`);
            }
        } catch (error) {
            console.error("Failed to start chat fetch:", error);
        }
    }

    async stopChatFetch(): Promise<void> {
        try {
            const response = await apiFetch("/api/streamChat/yt/stop", {
                method: "POST",
            });


            if (response.ok && this.socket) {
                this.isFetching = false;
                this.socket.close();
                this.socket = null;
            } else {
                console.error("Failed to stop chat fetch.");
            }
        } catch (error) {
            console.error("Failed to stop chat fetch:", error);
        }
    }

    closeSocket(): void {
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
    }

    isChatFetching(): boolean {
        return this.isFetching;
    }
}