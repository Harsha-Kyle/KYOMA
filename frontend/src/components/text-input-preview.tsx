import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Download, Mic, Volume2 } from "lucide-react"
import AudioPlayer from "@/components/audio-player"
import { ttsManager } from "@/lib/ttsManager"
import { toast } from "sonner"

export function TextInputPreview() {
  const [text, setText] = useState("")
  const [isGenerating, setIsGenerating] = useState(false)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)

  const handleGenerate = async () => {
    if (!text.trim()) return

    setIsGenerating(true)
    setAudioUrl(null)

    try {
      const url = await ttsManager.generateAudioFromText(text)
      setAudioUrl(url)
      const audio = new Audio(url)
      audio.play()
    } catch (error) {
      console.error("Error fetching TTS audio:", error)
      toast.error("Failed to generate audio. Please try again.")
    } finally {
      setIsGenerating(false)
    }
  }

  const handleDownload = () => {
    if (!audioUrl) return
    
    const a = document.createElement('a')
    a.href = audioUrl
    a.download = `tts-output-${Date.now()}.wav`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mic className="h-5 w-5" />
          Text Input & Preview
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="text-input">Text to synthesize</Label>
          <Textarea
            id="text-input"
            placeholder="Enter the text you want to convert to speech..."
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="min-h-[120px] resize-none"
          />
          <div className="text-sm text-slate-500">{text.length} characters</div>
        </div>

        <Separator />

        <div className="flex flex-col sm:flex-row gap-3">
          <Button onClick={handleGenerate} disabled={!text.trim() || isGenerating} className="flex-1">
            {isGenerating ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                Generating...
              </>
            ) : (
              <>
                <Volume2 className="h-4 w-4 mr-2" />
                Generate Speech
              </>
            )}
          </Button>

          <Button variant="outline" disabled={!audioUrl} onClick={handleDownload}>
            <Download className="h-4 w-4" />
          </Button>
        </div>

        {/* Audio Preview */}
        <div className="bg-accent rounded-lg p-4">
          {!audioUrl ? (
            <div className="text-center">
              Audio preview will appear here after generation
            </div>
          ) : (
            <AudioPlayer audioUrl={audioUrl} />
          )}
        </div>
      </CardContent>
    </Card>
  )
} 