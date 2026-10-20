import React, { useEffect, useState, useRef, useCallback } from "react";
import { apiFetch } from "@/lib/api-client";
import { ttsManager } from "@/lib/ttsManager";

interface LoadingScreenProps {
  onLoaded: () => void;
}

interface SubsystemTelemetry {
  tag: string;
  name: string;
  metric: string;
  status: "STANDBY" | "INITIALIZING" | "ONLINE";
}

const TARGET_WORLDLINE = "1.048596";
const INITIAL_WORLDLINE = "0.571024";

// Matrix / crypto stream characters
const STREAM_CHARS = "0123456789ABCDEF<>_/#$%*+=:;[]{}!?~^&|\\";

const BOOT_LOG_LINES = [
  "SYSTEM_INIT: Booting Kyoma Autonomous Engine...",
  "POST_CHECK: Kernel memory mapped & verified",
  "POST_CHECK: Core hardware acceleration active",
  "SUBSYS_LOAD: Mounting 16kHz audio I/O streaming receptor",
  "NEURAL_INIT: Initializing Ollama local LLM inference cluster",
  "KERNEL_SPAWN: Fast-API asynchronous RPC server active on :8000",
  "VOICE_SYNTH: Kokoro ONNX offline synthesizer loaded (54 voices)",
  "VECTOR_DB: Qdrant semantic memory index loaded & mapped",
  "SECURITY_GATE: Divergence matrix verification locked at 1.048596",
  "DISPATCHER: Handshake with Lab Terminal UI (:5173) verified",
  "PRE_CACHE: Hydrating session registries & character models",
  "CONVERGENCE: All cores nominal — entering cockpit interface",
];

export const LoadingScreen: React.FC<LoadingScreenProps> = ({ onLoaded }) => {
  const [progress, setProgress] = useState(6);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [backendConnected, setBackendConnected] = useState(false);
  const [isFinishing, setIsFinishing] = useState(false);
  const [divergenceDigits, setDivergenceDigits] = useState<string[]>(
    INITIAL_WORLDLINE.split("")
  );
  const [systemStateText, setSystemStateText] = useState("ESTABLISHING KERNEL PROTOCOLS...");
  const [terminalLog, setTerminalLog] = useState<string[]>([BOOT_LOG_LINES[0]]);
  const [oscilloBars, setOscilloBars] = useState<number[]>(
    Array.from({ length: 28 }, () => Math.random() * 45 + 5)
  );

  const [subsystems, setSubsystems] = useState<SubsystemTelemetry[]>([
    {
      tag: "CORE-01",
      name: "FASTAPI KERNEL",
      metric: "PORT 8000 // STANDBY",
      status: "INITIALIZING",
    },
    {
      tag: "NEUR-02",
      name: "COGNITIVE SYNAPSE",
      metric: "OLLAMA ENGINE // 0.0 T/S",
      status: "STANDBY",
    },
    {
      tag: "VECT-03",
      name: "VECTOR MEMORY",
      metric: "384-DIM EMBEDDINGS",
      status: "STANDBY",
    },
    {
      tag: "ACOU-04",
      name: "ACOUSTIC ENGINE",
      metric: "KOKORO 54V ONNX READY",
      status: "STANDBY",
    },
    {
      tag: "RECP-05",
      name: "AUDITORY RECEPTOR",
      metric: "WHISPER 16KHZ STREAM",
      status: "STANDBY",
    },
    {
      tag: "DIVR-06",
      name: "DIVERGENCE METER",
      metric: `RATIO ${TARGET_WORLDLINE}`,
      status: "INITIALIZING",
    },
  ]);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const gridCanvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);
  const gridAnimFrameRef = useRef<number>(0);
  const dropsRef = useRef<number[]>([]);
  const scrambleIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logLineIndexRef = useRef<number>(1);
  const termLogRef = useRef<HTMLDivElement>(null);

  // ── Background 1: Falling Cyan Code Rain (from Image 3) ──────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const fontSize = 13;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      const cols = Math.floor(canvas.width / fontSize);
      dropsRef.current = Array.from({ length: cols }, () =>
        Math.floor((Math.random() * -canvas.height) / fontSize)
      );
    };
    resize();
    window.addEventListener("resize", resize);

    const draw = () => {
      ctx.fillStyle = "rgba(2, 6, 12, 0.12)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.font = `${fontSize}px 'JetBrains Mono', 'Fira Code', monospace`;

      const cols = dropsRef.current.length;
      for (let i = 0; i < cols; i++) {
        const char = STREAM_CHARS[Math.floor(Math.random() * STREAM_CHARS.length)];
        const x = i * fontSize;
        const y = dropsRef.current[i] * fontSize;

        const isAmber = progress >= 95;
        // Head character
        ctx.fillStyle = isAmber ? "#fbbf24" : "#38bdf8";
        ctx.fillText(char, x, y);

        // Trail
        if (y > fontSize * 2) {
          ctx.fillStyle = isAmber ? "rgba(245, 158, 11, 0.15)" : "rgba(56, 189, 248, 0.14)";
          const trail = STREAM_CHARS[Math.floor(Math.random() * STREAM_CHARS.length)];
          ctx.fillText(trail, x, y - fontSize * 2);
        }

        if (y > canvas.height && Math.random() > 0.98) {
          dropsRef.current[i] = 0;
        }
        dropsRef.current[i]++;
      }

      animFrameRef.current = requestAnimationFrame(draw);
    };

    animFrameRef.current = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      window.removeEventListener("resize", resize);
    };
  }, [progress]);

  // ── Background 2: 3D Perspective Wireframe Grid (from Image 1) ───────────
  useEffect(() => {
    const canvas = gridCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let offset = 0;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    const drawGrid = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const w = canvas.width;
      const h = canvas.height;
      const horizonY = h * 0.62;
      const bottomY = h;

      ctx.strokeStyle = "rgba(14, 165, 233, 0.18)";
      ctx.lineWidth = 1;

      // Horizon line
      ctx.beginPath();
      ctx.moveTo(0, horizonY);
      ctx.lineTo(w, horizonY);
      ctx.stroke();

      // Perspective vertical lines fanning out
      const vpX = w / 2;
      const numLines = 32;
      for (let i = -numLines; i <= numLines; i++) {
        const xBottom = vpX + (i * (w / (numLines * 0.65)));
        ctx.beginPath();
        ctx.moveTo(vpX, horizonY);
        ctx.lineTo(xBottom, bottomY);
        ctx.stroke();
      }

      // Horizontal lines moving towards viewer
      offset = (offset + 0.5) % 30;
      for (let y = horizonY; y < bottomY; y += 14) {
        const progressFactor = (y - horizonY) / (bottomY - horizonY);
        const yPos = horizonY + Math.pow(progressFactor, 1.8) * (bottomY - horizonY);
        ctx.strokeStyle = `rgba(14, 165, 233, ${0.05 + progressFactor * 0.22})`;
        ctx.beginPath();
        ctx.moveTo(0, yPos);
        ctx.lineTo(w, yPos);
        ctx.stroke();
      }

      gridAnimFrameRef.current = requestAnimationFrame(drawGrid);
    };

    gridAnimFrameRef.current = requestAnimationFrame(drawGrid);

    return () => {
      cancelAnimationFrame(gridAnimFrameRef.current);
      window.removeEventListener("resize", resize);
    };
  }, []);

  // ── Oscilloscope waveform bars ────────────────────────────────────────────
  useEffect(() => {
    const t = setInterval(() => {
      setOscilloBars((prev) =>
        prev.map((v) => {
          const delta = (Math.random() - 0.5) * 26;
          return Math.max(6, Math.min(65, v + delta));
        })
      );
    }, 80);
    return () => clearInterval(t);
  }, []);

  // ── Nixie scramble ────────────────────────────────────────────────────────
  useEffect(() => {
    scrambleIntervalRef.current = setInterval(() => {
      if (progress < 96) {
        setDivergenceDigits((prev) =>
          prev.map((char, idx) => {
            if (char === ".") return ".";
            const lockThreshold = (idx / 8) * 100;
            if (progress > lockThreshold) return TARGET_WORLDLINE[idx];
            return String(Math.floor(Math.random() * 10));
          })
        );
      } else {
        setDivergenceDigits(TARGET_WORLDLINE.split(""));
      }
    }, 60);
    return () => {
      if (scrambleIntervalRef.current) clearInterval(scrambleIntervalRef.current);
    };
  }, [progress]);

  // ── Elapsed second counter ────────────────────────────────────────────────
  useEffect(() => {
    const t = setInterval(() => setElapsedSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);

  // ── Scrolling boot log ────────────────────────────────────────────────────
  useEffect(() => {
    const t = setInterval(() => {
      const idx = logLineIndexRef.current;
      if (idx < BOOT_LOG_LINES.length) {
        setTerminalLog((prev) => {
          const next = [...prev, BOOT_LOG_LINES[idx]];
          return next.slice(-7);
        });
        logLineIndexRef.current = idx + 1;
      }
    }, 3200);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (termLogRef.current) {
      termLogRef.current.scrollTop = termLogRef.current.scrollHeight;
    }
  }, [terminalLog]);

  // ── Smooth Cold-Boot Tracking & Complete Pre-Load Cycle ───────────────────
  const addLog = useCallback((msg: string) => {
    setTerminalLog((prev) => [...prev.slice(-6), msg]);
  }, []);

  useEffect(() => {
    let isCancelled = false;
    let pollInterval: ReturnType<typeof setInterval>;
    let currentPct = 6;

    const checkStatus = async () => {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);

        const res = await fetch("/api/status", {
          signal: controller.signal,
          headers: { "Cache-Control": "no-cache" },
        });
        clearTimeout(timeoutId);

        if (res.ok) {
          const data = await res.json();
          if (isCancelled) return;

          if (!backendConnected) {
            setBackendConnected(true);
            addLog(">>> KERNEL LINK ESTABLISHED [PORT 8000 ONLINE]");
          }

          if (data.ready) {
            clearInterval(pollInterval);
            setProgress(90);
            setSystemStateText("PRE-CACHING SYSTEM CONFIG & NEURAL ASSETS...");
            addLog(">>> Backend converged. Performing full state pre-cache...");

            // Pre-load all primary assets simultaneously
            try {
              const [settingsRes, sessionsRes, modelsRes, voicesRes, kokoroRes, live2dRes, vrmRes] =
                await Promise.allSettled([
                  apiFetch("/api/settings"),
                  apiFetch("/api/chat/sessions"),
                  apiFetch("/api/llm/models"),
                  apiFetch("/api/tts/voices"),
                  apiFetch("/api/tts/kokoro/voices"),
                  apiFetch("/api/character/live2d/models"),
                  apiFetch("/api/character/vrm/models"),
                ]);

              if (settingsRes.status === "fulfilled" && settingsRes.value) {
                try {
                  const sData = await settingsRes.value.json();
                  if (sData?.settings) {
                    window.__kyoma_settings_cache = sData.settings;
                    if (sData.settings["tts.provider"]) {
                      ttsManager.syncProviderFromCache(sData.settings["tts.provider"]);
                    }
                  }
                } catch (_) {}
              }

              if (sessionsRes.status === "fulfilled" && sessionsRes.value) {
                try {
                  const sessData = await sessionsRes.value.json();
                  if (Array.isArray(sessData)) {
                    window.__kyoma_sessions_cache = sessData;
                  }
                } catch (_) {}
              }

              if (modelsRes.status === "fulfilled" && modelsRes.value) {
                try {
                  const mData = await modelsRes.value.json();
                  if (mData?.models) {
                    window.__kyoma_models_cache = mData;
                  }
                } catch (_) {}
              }
            } catch (err) {
              console.warn("[LoadingScreen] Asset preload warning:", err);
            }

            if (isCancelled) return;

            setProgress(96);
            setSystemStateText("HYDRATING COCKPIT REGISTRY & DIALOGUE REPOSITORY...");
            addLog(">>> Pre-cache verified. Initializing cockpit telemetry...");

            await new Promise((r) => setTimeout(r, 400));
            if (isCancelled) return;

            setProgress(100);
            setDivergenceDigits(TARGET_WORLDLINE.split(""));
            setSystemStateText("ALL SYSTEMS SYNCHRONIZED // ENTERING TERMINAL");
            addLog(">>> Divergence ratio locked at 1.048596. Welcome back.");
            setSubsystems((prev) => prev.map((s) => ({ ...s, status: "ONLINE" })));

            setIsFinishing(true);
            setTimeout(() => {
              if (!isCancelled) onLoaded();
            }, 600);
            return;
          } else {
            // Backend is up but not ready yet (e.g. running startup steps)
            const targetPct = Math.max(55, Math.min(88, data.percentage || 72));
            currentPct = Math.max(currentPct, targetPct);
            setProgress(currentPct);
            setSystemStateText(data.message?.toUpperCase() || "STARTING REASONING DAEMON...");
            if (data.message) addLog(`>>> ${data.message}`);

            setSubsystems((prev) => [
              { ...prev[0], status: "ONLINE", metric: "PORT 8000 // ONLINE" },
              {
                ...prev[1],
                status: data.step >= 2 ? "ONLINE" : "INITIALIZING",
                metric: data.step >= 2 ? "NEURAL POOL ACTIVE" : "STARTING OLLAMA...",
              },
              {
                ...prev[2],
                status: data.step >= 3 ? "ONLINE" : "INITIALIZING",
                metric: data.step >= 3 ? "QDRANT ACTIVE" : "EMBEDDING VECTOR...",
              },
              {
                ...prev[3],
                status: data.step >= 4 ? "ONLINE" : "INITIALIZING",
                metric: data.step >= 4 ? "KOKORO 54V ONLINE" : "ONNX WARMUP...",
              },
              { ...prev[4], status: data.step >= 2 ? "ONLINE" : "STANDBY", metric: "16KHZ AUDIO PIPE" },
              { ...prev[5], status: "ONLINE", metric: `RATIO ${TARGET_WORLDLINE}` },
            ]);
          }
        }
      } catch {
        // Backend not yet reachable (typical during cold boot Python/Torch import phase)
        if (isCancelled) return;
        setBackendConnected(false);

        // Smooth predictable advance from 6% to 86% based on time elapsed
        setElapsedSeconds((sec) => {
          let calculatedPct = 6;
          if (sec < 10) {
            calculatedPct = 6 + (sec / 10) * 18; // 6% -> 24%
            setSystemStateText("BOOT: LOADING PYTHON RUNTIME & PYTORCH MODULES...");
          } else if (sec < 25) {
            calculatedPct = 24 + ((sec - 10) / 15) * 28; // 24% -> 52%
            setSystemStateText("INITIALIZING OLLAMA ENGINE & SCANNING HARDWARE...");
          } else if (sec < 40) {
            calculatedPct = 52 + ((sec - 25) / 15) * 24; // 52% -> 76%
            setSystemStateText("STARTING FASTAPI CORE & VOICE SYNTHESIS...");
          } else {
            calculatedPct = Math.min(88, 76 + ((sec - 40) / 15) * 12); // 76% -> 88%
            setSystemStateText("FINALIZING VECTOR INDEXES & SOCKET DISPATCH...");
          }
          currentPct = Math.max(currentPct, Math.round(calculatedPct));
          setProgress(currentPct);
          return sec;
        });
      }
    };

    checkStatus();
    pollInterval = setInterval(checkStatus, 700);

    return () => {
      isCancelled = true;
      clearInterval(pollInterval);
    };
  }, [onLoaded, addLog]);

  // Segmented block bar calculation (28 blocks, Image 2 style)
  const TOTAL_SEGMENTS = 28;
  const activeSegments = Math.round((progress / 100) * TOTAL_SEGMENTS);

  // Circular Dial Segment Calculation (36 segments for central ring)
  const DIAL_SEGMENTS = 36;
  const activeDialSegments = Math.round((progress / 100) * DIAL_SEGMENTS);

  const formattedTime = `${String(Math.floor(elapsedSeconds / 60)).padStart(2, "0")}:${String(
    elapsedSeconds % 60
  ).padStart(2, "0")}`;

  return (
    <div
      className={`fixed inset-0 z-50 flex flex-col justify-between bg-[#02050b] text-[#e0f2fe] font-mono select-none overflow-hidden transition-opacity duration-700 ${
        isFinishing ? "opacity-0 pointer-events-none" : "opacity-100"
      }`}
    >
      {/* ── Background Layer 1: Cyan Data Rain Canvas (Image 3) ──────────────── */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 pointer-events-none z-0 opacity-30"
      />

      {/* ── Background Layer 2: 3D Perspective Grid Horizon (Image 1) ───────── */}
      <canvas
        ref={gridCanvasRef}
        className="absolute inset-0 pointer-events-none z-0 opacity-75"
      />

      {/* ── CRT Optical Scanlines ───────────────────────────────────────────── */}
      <div
        className="absolute inset-0 pointer-events-none z-10"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.18) 2px, rgba(0,0,0,0.18) 4px)",
        }}
      />

      {/* ── Vignette Edge Shadow ────────────────────────────────────────────── */}
      <div
        className="absolute inset-0 pointer-events-none z-10"
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 40%, rgba(2, 6, 18, 0.82) 100%)",
        }}
      />

      {/* ═══════════════════════════════════════════════════════════════════════
          HEADER BAR: Cockpit Telemetry & Segmented Download Bar (Image 2)
      ═══════════════════════════════════════════════════════════════════════ */}
      <header className="relative z-20 w-full border-b border-sky-900/60 bg-[#030914]/90 backdrop-blur-md px-6 py-3 flex flex-wrap items-center justify-between gap-4">
        {/* Branding & Status */}
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center">
            <span
              className={`w-3 h-3 rounded-sm ${
                backendConnected
                  ? "bg-emerald-400 shadow-[0_0_12px_#34d399]"
                  : "bg-sky-400 shadow-[0_0_12px_#38bdf8] animate-pulse"
              }`}
            />
          </div>
          <div className="flex flex-col">
            <span className="font-extrabold text-sky-300 text-xs tracking-[0.25em] drop-shadow-[0_0_8px_#38bdf8]">
              KYOMA // COCKPIT HUD
            </span>
            <span className="text-[10px] text-sky-600 tracking-wider">
              OPERATIONAL WORLDLINE MATRIX v2.5
            </span>
          </div>
        </div>

        {/* Top Segmented Progress Bar ("DOWNLOAD PROGRESS" from Image 2) */}
        <div className="flex flex-col items-center gap-1.5 flex-1 max-w-xl mx-auto px-4">
          <div className="flex justify-between w-full text-[10px] text-sky-400 tracking-widest font-bold">
            <span className="flex items-center gap-2">
              <span className="inline-block w-1.5 h-1.5 bg-amber-400 rounded-full animate-ping" />
              SYSTEM CONVERGENCE PROGRESS
            </span>
            <span className="text-amber-400 font-extrabold">{progress}%</span>
          </div>
          {/* Segmented blocks */}
          <div className="flex items-center gap-1 w-full bg-[#040e1e] p-1 border border-sky-900/80 rounded-none shadow-[inset_0_0_10px_rgba(56,189,248,0.15)]">
            {Array.from({ length: TOTAL_SEGMENTS }).map((_, i) => {
              const isLit = i < activeSegments;
              const isLead = i === activeSegments - 1;
              return (
                <div
                  key={i}
                  className={`h-4 flex-1 rounded-[1px] transition-all duration-300 ${
                    isLit
                      ? isLead
                        ? "bg-amber-300 shadow-[0_0_10px_#fde047]"
                        : i % 2 === 0
                        ? "bg-amber-500 shadow-[0_0_6px_#f59e0b]"
                        : "bg-sky-400 shadow-[0_0_6px_#38bdf8]"
                      : "bg-sky-950/40 border border-sky-900/20"
                  }`}
                />
              );
            })}
          </div>
        </div>

        {/* Header Telemetry Badges */}
        <div className="flex items-center gap-5 text-[11px] text-slate-400 font-mono">
          <div className="hidden sm:flex items-center gap-2">
            <span className="text-sky-700">LINK:</span>
            <span className={backendConnected ? "text-emerald-400 font-bold" : "text-sky-400 animate-pulse"}>
              {backendConnected ? "ONLINE:8000" : "HANDSHAKE"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sky-700">UPTIME:</span>
            <span className="text-sky-300 font-bold">T+{formattedTime}</span>
          </div>
        </div>
      </header>

      {/* ═══════════════════════════════════════════════════════════════════════
          MAIN WORKSPACE: HUD Instrument Clusters (Images 1, 2)
      ═══════════════════════════════════════════════════════════════════════ */}
      <main className="relative z-20 flex-1 px-4 sm:px-8 py-3 flex flex-col justify-between max-w-[1550px] mx-auto w-full overflow-hidden">
        
        {/* ROW 1: Centerpiece Hero Area */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center my-auto">
          
          {/* Left Column: Subsystem Cards (from Image 1 & 2) */}
          <div className="lg:col-span-3 flex flex-col gap-2.5">
            <div className="flex justify-between items-center text-[10px] text-sky-400 tracking-widest border-b border-sky-900/60 pb-1">
              <span className="font-bold flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 bg-sky-400 rounded-sm" />
                CORE SUBSYSTEMS
              </span>
              <span className="text-sky-600">CLUSTER 01</span>
            </div>

            <div className="grid grid-cols-1 gap-2">
              {subsystems.slice(0, 3).map((s) => (
                <div
                  key={s.tag}
                  className={`border p-2.5 bg-[#040d1a]/85 backdrop-blur-sm transition-all duration-300 ${
                    s.status === "ONLINE"
                      ? "border-emerald-700/60 shadow-[0_0_12px_rgba(16,185,129,0.12)] text-emerald-300"
                      : s.status === "INITIALIZING"
                      ? "border-amber-600/70 shadow-[0_0_12px_rgba(245,158,11,0.12)] text-amber-300"
                      : "border-sky-950 text-slate-500"
                  }`}
                >
                  <div className="flex justify-between text-[10px] mb-1">
                    <span className="font-bold tracking-wider text-sky-300">{s.tag}</span>
                    <span
                      className={`font-extrabold tracking-widest text-[9px] ${
                        s.status === "ONLINE"
                          ? "text-emerald-400"
                          : s.status === "INITIALIZING"
                          ? "text-amber-400 animate-pulse"
                          : "text-slate-600"
                      }`}
                    >
                      {s.status}
                    </span>
                  </div>
                  <div className="font-bold text-xs text-white tracking-wide">{s.name}</div>
                  <div className="text-[10px] text-sky-600/90 font-mono mt-1 border-t border-sky-950/60 pt-1">
                    {s.metric}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Center Column: Giant Segmented Rotating Ring Dial (Image 2 Cockpit Dial) */}
          <div className="lg:col-span-6 flex flex-col items-center justify-center p-2 relative">
            <div className="relative w-64 h-64 sm:w-80 sm:h-80 flex items-center justify-center">
              
              {/* Outer Rotating Compass Ticks Ring */}
              <svg
                className="absolute inset-0 w-full h-full animate-[spin_40s_linear_infinite]"
                viewBox="0 0 300 300"
              >
                <circle
                  cx="150"
                  cy="150"
                  r="142"
                  fill="none"
                  stroke="rgba(56, 189, 248, 0.25)"
                  strokeWidth="1.5"
                  strokeDasharray="4 8"
                />
                <circle
                  cx="150"
                  cy="150"
                  r="132"
                  fill="none"
                  stroke="rgba(56, 189, 248, 0.15)"
                  strokeWidth="1"
                />
                {/* Degree indicators */}
                <text x="145" y="18" fill="#38bdf8" fontSize="8" fontFamily="monospace">0°</text>
                <text x="282" y="153" fill="#38bdf8" fontSize="8" fontFamily="monospace">90°</text>
                <text x="142" y="292" fill="#38bdf8" fontSize="8" fontFamily="monospace">180°</text>
                <text x="8" y="153" fill="#38bdf8" fontSize="8" fontFamily="monospace">270°</text>
              </svg>

              {/* Segmented Circular Ring Meter (Image 2 style) */}
              <svg className="absolute inset-0 w-full h-full -rotate-90" viewBox="0 0 300 300">
                {Array.from({ length: DIAL_SEGMENTS }).map((_, i) => {
                  const angle = (i / DIAL_SEGMENTS) * 360;
                  const rad = (angle * Math.PI) / 180;
                  const rInner = 98;
                  const rOuter = 118;
                  const x1 = 150 + rInner * Math.cos(rad);
                  const y1 = 150 + rInner * Math.sin(rad);
                  const x2 = 150 + rOuter * Math.cos(rad);
                  const y2 = 150 + rOuter * Math.sin(rad);
                  const isLit = i < activeDialSegments;
                  const isLead = i === activeDialSegments - 1;

                  return (
                    <line
                      key={i}
                      x1={x1}
                      y1={y1}
                      x2={x2}
                      y2={y2}
                      stroke={
                        isLit
                          ? isLead
                            ? "#fbbf24"
                            : i % 3 === 0
                            ? "#f59e0b"
                            : "#38bdf8"
                          : "rgba(14, 116, 144, 0.25)"
                      }
                      strokeWidth={isLit ? "5" : "3"}
                      strokeLinecap="round"
                      style={
                        isLit
                          ? { filter: "drop-shadow(0 0 6px rgba(56, 189, 248, 0.8))" }
                          : undefined
                      }
                    />
                  );
                })}
              </svg>

              {/* Radar Sweeping Hand Line */}
              <div
                className="absolute w-28 h-0.5 bg-gradient-to-r from-transparent to-sky-400 origin-left left-1/2 top-1/2 animate-[spin_3s_linear_infinite]"
                style={{
                  boxShadow: "0 0 10px #38bdf8",
                }}
              />

              {/* Center Holographic Core Display */}
              <div className="relative z-10 flex flex-col items-center justify-center bg-[#030914]/90 border border-sky-800/80 rounded-full w-36 h-36 sm:w-44 sm:h-44 shadow-[0_0_35px_rgba(56,189,248,0.25)] backdrop-blur-md">
                <span className="text-[9px] tracking-[0.25em] text-sky-400 font-bold uppercase mb-1">
                  CONVERGENCE
                </span>
                <span
                  className="text-4xl sm:text-5xl font-black font-mono tracking-tight text-white drop-shadow-[0_0_15px_#38bdf8]"
                >
                  {progress}%
                </span>
                <span className="text-[10px] text-amber-400 font-bold mt-1 tracking-widest flex items-center gap-1">
                  <span className="w-1.5 h-1.5 bg-amber-400 rounded-full animate-ping" />
                  {backendConnected ? "SYNCHRONIZED" : "INITIALIZING"}
                </span>
              </div>
            </div>

            {/* Current State Indicator Banner */}
            <div className="mt-3 text-center px-4 py-1.5 bg-[#051124]/80 border border-sky-900/60 text-sky-300 text-xs tracking-wider flex items-center gap-2 shadow-[0_0_15px_rgba(56,189,248,0.1)]">
              <span className="text-amber-400 font-mono font-bold">&gt;&gt;</span>
              <span className="font-semibold uppercase truncate">{systemStateText}</span>
            </div>
          </div>

          {/* Right Column: Audio Waveform & Nixie Telemetry */}
          <div className="lg:col-span-3 flex flex-col gap-2.5">
            <div className="flex justify-between items-center text-[10px] text-sky-400 tracking-widest border-b border-sky-900/60 pb-1">
              <span className="font-bold flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 bg-amber-400 rounded-sm" />
                TELEMETRY & SENSORS
              </span>
              <span className="text-sky-600">CLUSTER 02</span>
            </div>

            {/* Physical Nixie Tube Divergence Ratio (Steins Gate homage) */}
            <div className="border border-amber-900/70 bg-[#0c0703]/90 p-3 shadow-[0_0_20px_rgba(245,158,11,0.08)]">
              <div className="flex justify-between text-[9px] text-amber-500 font-bold tracking-widest mb-1.5">
                <span>DIVERGENCE RATIO</span>
                <span className={progress >= 96 ? "text-emerald-400" : "animate-pulse"}>
                  {progress >= 96 ? "LOCKED" : "CONVERGING"}
                </span>
              </div>
              <div className="flex items-center justify-center gap-1 bg-[#050201] p-1.5 border border-amber-950">
                {divergenceDigits.map((digit, idx) => (
                  <div
                    key={idx}
                    className={`flex items-center justify-center ${
                      digit === "."
                        ? "w-2.5 h-9"
                        : "w-6 sm:w-7 h-9 bg-[#170a02] border border-amber-800/80 shadow-[inset_0_0_8px_rgba(245,158,11,0.3)]"
                    }`}
                  >
                    <span
                      className={`font-serif font-black ${
                        digit === "."
                          ? "text-lg text-amber-400 drop-shadow-[0_0_6px_#f59e0b]"
                          : "text-xl text-amber-300 drop-shadow-[0_0_8px_#f59e0b]"
                      }`}
                    >
                      {digit}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Audio Waveform Equalizer */}
            <div className="border border-sky-900/60 bg-[#040e1d]/85 p-3">
              <div className="flex justify-between text-[9px] text-sky-400 font-bold tracking-wider mb-2">
                <span>SPEECH HARMONICS</span>
                <span className="text-sky-500 font-mono">16.0 KHZ</span>
              </div>
              <div className="flex items-end gap-1 h-12 w-full justify-between">
                {oscilloBars.map((h, i) => (
                  <div
                    key={i}
                    className="flex-1 transition-all duration-100 rounded-t-[1px]"
                    style={{
                      height: `${h}%`,
                      backgroundColor:
                        progress >= 95
                          ? `rgba(251, 191, 36, ${0.4 + (i % 2) * 0.4})`
                          : `rgba(56, 189, 248, ${0.35 + (i % 2) * 0.45})`,
                      boxShadow: progress >= 95 ? "0 0 6px #fbbf24" : "0 0 6px #38bdf8",
                    }}
                  />
                ))}
              </div>
            </div>

            {/* Subsystems 4 & 5 */}
            {subsystems.slice(3, 5).map((s) => (
              <div
                key={s.tag}
                className="border border-sky-950 p-2 bg-[#040d1a]/85 text-slate-400 flex justify-between items-center text-[10px]"
              >
                <div>
                  <span className="text-sky-400 font-bold mr-1.5">{s.tag}</span>
                  <span className="text-white font-medium">{s.name}</span>
                </div>
                <span className="text-sky-500 font-mono text-[9px]">{s.metric}</span>
              </div>
            ))}
          </div>

        </div>

        {/* ROW 2: Boot Stream Terminal Console (Image 1, 3) */}
        <div className="border border-sky-900/60 bg-[#020712]/95 p-3 mt-3 shadow-[0_0_20px_rgba(56,189,248,0.06)]">
          <div className="flex justify-between items-center text-[10px] text-sky-400 font-bold border-b border-sky-950 pb-1.5 mb-2">
            <span className="flex items-center gap-2">
              <span className="text-cyan-400">&gt;_</span> REAL-TIME KERNEL LOG STREAM
            </span>
            <div className="flex gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-500/70" />
              <span className="w-2 h-2 rounded-full bg-amber-500/70" />
              <span className="w-2 h-2 rounded-full bg-emerald-500/70" />
            </div>
          </div>
          <div
            ref={termLogRef}
            className="h-20 overflow-y-auto space-y-1 font-mono text-[10px] text-slate-400 scrollbar-thin scrollbar-thumb-sky-900/50"
          >
            {terminalLog.map((line, i) => (
              <div key={i} className="flex gap-2 leading-relaxed">
                <span className="text-sky-600 select-none font-bold">&gt;&gt;</span>
                <span
                  className={
                    i === terminalLog.length - 1
                      ? "text-sky-300 font-semibold drop-shadow-[0_0_6px_#38bdf8]"
                      : "text-slate-500"
                  }
                >
                  {line}
                </span>
              </div>
            ))}
            <div className="flex gap-2">
              <span className="text-sky-600 font-bold">&gt;&gt;</span>
              <span className="text-sky-400 animate-pulse font-bold">█</span>
            </div>
          </div>
        </div>

      </main>

      {/* ═══════════════════════════════════════════════════════════════════════
          FOOTER BAR: Telemetry Link Protocol (Image 1)
      ═══════════════════════════════════════════════════════════════════════ */}
      <footer className="relative z-20 w-full border-t border-sky-900/60 bg-[#030814]/90 px-6 py-2 flex items-center justify-between text-[10px] text-slate-500 font-mono tracking-wider">
        <div className="flex items-center gap-4">
          <span>HOST: 127.0.0.1:8000</span>
          <span className="hidden sm:inline">BUFFER: 16000HZ PCM</span>
          <span className="hidden md:inline">ENCODING: ONNX FP32</span>
          <span className="hidden lg:inline">WORLDLINE: 1.048596</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-slate-600">OPERATION CONVERGENCE</span>
          <span className="text-amber-500 font-bold tracking-[0.2em] drop-shadow-[0_0_8px_#f59e0b]">
            EL PSY KONGROO
          </span>
        </div>
      </footer>
    </div>
  );
};

export default LoadingScreen;
