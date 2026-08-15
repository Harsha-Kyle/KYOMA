export abstract class BaseTTSProvider {
    abstract generateAudio(text: string): Promise<Response>;
}