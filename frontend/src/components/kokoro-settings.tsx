import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import { ttsManager } from "@/lib/ttsManager";
import { KokoroProvider, KokoroVoice } from "@/lib/tts/kokoroProvider";
import {
    Select,
    SelectContent,
    SelectGroup,
    SelectItem,
    SelectLabel,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Mic2, Gauge, Info } from "lucide-react";

export default function KokoroSettings() {
    const provider = ttsManager.getCurrentProviderInstance() as KokoroProvider;

    const [voices, setVoices] = useState<KokoroVoice[]>([]);
    const [currentVoice, setCurrentVoice] = useState<string | null>(null);
    const [speed, setSpeed] = useState<number>(1.0);
    const [isAvailable, setIsAvailable] = useState<boolean>(false);

    useEffect(() => {
        provider.refreshVoices().then(() => {
            setVoices(provider.getVoices());
            setCurrentVoice(provider.getCurrentVoice());
            setSpeed(provider.getSpeed());
            setIsAvailable(provider.getVoices().length > 0);
        });

        const unsubscribe = provider.subscribe(() => {
            setVoices(provider.getVoices());
            setCurrentVoice(provider.getCurrentVoice());
            setSpeed(provider.getSpeed());
            setIsAvailable(provider.getVoices().length > 0);
        });

        return unsubscribe;
    }, [provider]);

    const handleVoiceChange = async (voiceId: string) => {
        try {
            await provider.setVoice(voiceId);
            setCurrentVoice(voiceId);
        } catch (e) {
            console.error("[KokoroSettings] Failed to change voice:", e);
        }
    };

    const handleSpeedChange = async (value: number[]) => {
        const s = value[0];
        setSpeed(s);
        try {
            await provider.setSpeed(s);
        } catch (e) {
            console.error("[KokoroSettings] Failed to set speed:", e);
        }
    };

    // Group voices by lang label
    const grouped = voices.reduce<Record<string, KokoroVoice[]>>((acc, v) => {
        if (!acc[v.lang]) acc[v.lang] = [];
        acc[v.lang].push(v);
        return acc;
    }, {});

    if (!isAvailable) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Mic2 className="h-5 w-5" />
                        Kokoro Settings
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-start gap-3 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-4">
                        <Info className="h-5 w-5 mt-0.5 text-yellow-500 shrink-0" />
                        <div className="space-y-1 text-sm">
                            <p className="font-medium text-yellow-500">Model files not found</p>
                            <p className="text-muted-foreground">
                                Kokoro model files are missing. The backend will attempt to
                                download them automatically on first use, or you can run:
                            </p>
                            <code className="block mt-1 rounded bg-muted px-2 py-1 text-xs">
                                python download_kokoro_weights.py
                            </code>
                            <p className="text-muted-foreground mt-1">
                                Files required in{" "}
                                <code className="text-xs">backend/services/TTS/Kokoro/models/</code>
                            </p>
                        </div>
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Mic2 className="h-5 w-5" />
                    Kokoro Settings
                    <Badge variant="secondary" className="ml-1 text-xs">Offline</Badge>
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">

                {/* Voice selector */}
                <div className="space-y-2">
                    <Label className="flex items-center gap-1">
                        <Mic2 className="h-4 w-4" /> Voice
                    </Label>
                    <Select
                        value={currentVoice ?? ""}
                        onValueChange={handleVoiceChange}
                    >
                        <SelectTrigger className="w-full">
                            <SelectValue placeholder="Select a voice…" />
                        </SelectTrigger>
                        <SelectContent className="max-h-72">
                            {Object.entries(grouped).map(([lang, group]) => (
                                <SelectGroup key={lang}>
                                    <SelectLabel>{lang}</SelectLabel>
                                    {group.map((v) => (
                                        <SelectItem key={v.id} value={v.id}>
                                            {v.id}
                                        </SelectItem>
                                    ))}
                                </SelectGroup>
                            ))}
                        </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                        {voices.length} built-in voices — no internet required.
                    </p>
                </div>

                {/* Speed slider */}
                <div className="space-y-3">
                    <Label className="flex items-center gap-1">
                        <Gauge className="h-4 w-4" /> Speed — {speed.toFixed(2)}×
                    </Label>
                    <Slider
                        min={0.5}
                        max={2.0}
                        step={0.05}
                        value={[speed]}
                        onValueChange={handleSpeedChange}
                    />
                    <p className="text-xs text-muted-foreground">
                        0.5× (slow) → 1.0× (normal) → 2.0× (fast)
                    </p>
                </div>
            </CardContent>
        </Card>
    );
}
