"use client"

import { useState, useRef } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Badge } from "@/components/ui/badge"
import { Upload, FileText, Trash2, Download, AlertCircle, CheckCircle2, MoreVertical } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { TTSVoice } from "@/lib/tts/gptsovitsProvider"

const LANGUAGES = {
  'zh': 'Chinese',
  'ja': 'Japanese',
  'en': 'English',
  'ko': 'Korean',
  'yue': 'Cantonese'
} as const;

interface VoiceUploadManagerProps {
  voices: TTSVoice[]
  onVoicesChange?: () => void
}

export default function GptSovitsUploadManager({ voices, onVoicesChange }: VoiceUploadManagerProps) {
  const [open, setOpen] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "success" | "error">("idle")
  const [formData, setFormData] = useState({
    name: "",
    referenceText: "",
    referenceLanguage: "en",
  })
  const [audioFile, setAudioFile] = useState<File | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleVoiceUpload = async () => {
    if (!audioFile || !formData.name || !formData.referenceText) return

    setUploadStatus("uploading")

    try {
      const formDataToSend = new FormData()
      formDataToSend.append("name", formData.name)
      formDataToSend.append("reference_audio", audioFile)
      formDataToSend.append("reference_text", formData.referenceText)
      formDataToSend.append("reference_language", formData.referenceLanguage)

      const response = await fetch("/api/tts/upload", {
        method: "POST",
        body: formDataToSend,
      })

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`)
      }

      setUploadStatus("success")
      onVoicesChange?.()
      
      // Reset form
      setFormData({
        name: "",
        referenceText: "",
        referenceLanguage: "en",
      })
      setAudioFile(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
    } catch (error) {
      console.error("Upload error:", error)
      setUploadStatus("error")
    }

    setTimeout(() => setUploadStatus("idle"), 2000)
  }

  const handleDeleteVoice = async (voice: TTSVoice) => {
    try {
      const response = await fetch("/api/tts/delete", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: voice.name }),
      })

      if (!response.ok) {
        throw new Error(`Delete failed: ${response.statusText}`)
      }

      onVoicesChange?.()
    } catch (error) {
      console.error("Delete error:", error)
    }
  }

  return (
    <div className="w-full">
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button size="lg" className="gap-2 w-full">
            <Upload className="h-4 w-4" />
            Manage Voice Models
          </Button>
        </DialogTrigger>
        <DialogContent className="max-h-[80vh] flex flex-col overflow-y-auto scrollbar-hide">
          <DialogHeader>
            <DialogTitle>Voice Model Manager</DialogTitle>
            <DialogDescription>
              Upload voice samples with reference text for GPT-SoVITS voice models.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-6 w-full">
            {/* Upload Section */}
            <Card className="w-full">
              <CardContent className="space-y-4">
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="name">Voice Name</Label>
                    <Input
                      id="name"
                      placeholder="e.g., my_voice"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="audio">Reference Audio</Label>
                    <p className="text-sm text-muted-foreground">Upload a 3-10 seconds audio file of clear speech</p>
                    <Input
                      id="audio"
                      ref={fileInputRef}
                      type="file"
                      accept="audio/*"
                      onChange={(e) => {
                        // Just store the file, don't upload yet
                        const files = e.target.files;
                        if (files) {
                          setAudioFile(files[0]);
                        }
                      }}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="text">Reference Text</Label>
                    <Input
                      id="text"
                      placeholder="Enter the text that matches the audio"
                      value={formData.referenceText}
                      onChange={(e) => setFormData({ ...formData, referenceText: e.target.value })}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="language">Language</Label>
                    <Select
                      value={formData.referenceLanguage}
                      onValueChange={(value) => setFormData({ ...formData, referenceLanguage: value })}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select a language" />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(LANGUAGES).map(([code, name]) => (
                          <SelectItem key={code} value={code}>
                            {name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <Button
                    className="w-full"
                    onClick={() => handleVoiceUpload()}
                    disabled={!audioFile || !formData.name || !formData.referenceText || uploadStatus === "uploading"}
                  >
                    {uploadStatus === "uploading" ? (
                      <>Uploading...</>
                    ) : (
                      <>
                        <Upload className="h-4 w-4 mr-2" />
                        Upload Voice
                      </>
                    )}
                  </Button>
                </div>

                {/* Upload Status */}
                {uploadStatus !== "idle" && (
                  <Alert className={uploadStatus === "error" ? "border-destructive" : ""}>
                    {uploadStatus === "uploading" && <AlertCircle className="h-4 w-4" />}
                    {uploadStatus === "success" && <CheckCircle2 className="h-4 w-4 text-green-600" />}
                    {uploadStatus === "error" && <AlertCircle className="h-4 w-4 text-destructive" />}
                    <AlertDescription>
                      {uploadStatus === "uploading" && "Uploading voice model..."}
                      {uploadStatus === "success" && "Voice model uploaded successfully!"}
                      {uploadStatus === "error" && "Upload failed. Please try again."}
                    </AlertDescription>
                  </Alert>
                )}
              </CardContent>
            </Card>

            <Separator />

            {/* Existing Models Section */}
            <Card className="w-full">
              <CardHeader>
                <CardTitle className="text-lg">Existing Voice Models ({voices.length})</CardTitle>
                <CardDescription>Manage your uploaded voice models</CardDescription>
              </CardHeader>
              <CardContent>
                {voices.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>No voice models uploaded yet</p>
                    <p className="text-sm">Upload your first voice model to get started</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {voices.map((voice) => (
                      <div
                        key={voice.name}
                        className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 transition-colors"
                      >
                        <div className="flex items-center gap-4">
                          <div className="p-2 rounded-md bg-primary/10">
                            <FileText className="h-5 w-5 text-primary" />
                          </div>
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <h4 className="font-medium">{voice.displayName || voice.name}</h4>
                              <Badge variant="secondary">AUDIO</Badge>
                            </div>
                          </div>
                        </div>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon">
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem className="gap-2" onClick={() => window.open(`/api/tts/download/${encodeURIComponent(voice.name)}`)}>
                              <Download className="h-4 w-4" />
                              Download
                            </DropdownMenuItem>
                            <DropdownMenuItem className="gap-2 text-destructive" onClick={() => handleDeleteVoice(voice)}>
                              <Trash2 className="h-4 w-4" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
