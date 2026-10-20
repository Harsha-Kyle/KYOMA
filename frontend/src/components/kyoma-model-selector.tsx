import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";

interface OllamaModel {
  fileName: string;
  provider: string;
  displayName?: string;
}

export function KyomaModelSelector() {
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [currentModel, setCurrentModel] = useState<string>("gemma4:e2b");
  const [loading, setLoading] = useState(false);

  const fetchModels = async () => {
    setLoading(true);
    try {
      const res = await apiFetch("/api/llm/models");
      if (res.ok) {
        const data = await res.json();
        const ollamaModels: OllamaModel[] = (data.models ?? []).filter(
          (m: OllamaModel) => m.provider === "ollama"
        );
        setModels(ollamaModels);
      }
    } catch (e) {
      console.error("[KyomaModelSelector] Failed to fetch models:", e);
    } finally {
      setLoading(false);
    }
  };

  const fetchCurrentModel = async () => {
    try {
      const res = await apiFetch("/api/kyoma/model");
      if (res.ok) {
        const data = await res.json();
        setCurrentModel(data.model ?? "gemma4:e2b");
      }
    } catch (e) {
      console.error("[KyomaModelSelector] Failed to fetch current model:", e);
    }
  };

  useEffect(() => {
    fetchModels();
    fetchCurrentModel();
  }, []);

  const handleChange = async (value: string) => {
    setCurrentModel(value);
    try {
      await apiFetch("/api/kyoma/model", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: value }),
      });
    } catch (e) {
      console.error("[KyomaModelSelector] Failed to set model:", e);
    }
  };

  const handleRefresh = () => {
    fetchModels();
    fetchCurrentModel();
  };

  return (
    <div className="flex flex-row items-center gap-2 w-full">
      <Select value={currentModel} onValueChange={handleChange}>
        <SelectTrigger className="flex-1">
          <SelectValue placeholder={currentModel || "Select Kyoma Model"} />
        </SelectTrigger>
        <SelectContent>
          {models.length === 0 ? (
            <SelectItem value={currentModel || "gemma4:e2b"}>
              {currentModel || "gemma4:e2b"}
            </SelectItem>
          ) : (
            models.map((m) => (
              <SelectItem key={m.fileName} value={m.fileName}>
                {m.displayName ?? m.fileName}
              </SelectItem>
            ))
          )}
        </SelectContent>
      </Select>
      <Button
        variant="ghost"
        size="icon"
        onClick={handleRefresh}
        disabled={loading}
        title="Refresh models"
      >
        <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
      </Button>
    </div>
  );
}

export default KyomaModelSelector;
