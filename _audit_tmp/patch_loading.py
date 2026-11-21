path = r'LocalAIVtuber2-master\frontend\src\components\loading-screen.tsx'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

old = '''        // Smooth predictable advance from 6% to 86% based on time elapsed
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
        });'''

new = '''        // Smooth predictable advance from 6% to 50% based on measured stage durations:
        // Python imports dominate cold boot at ~60s. Server only responds after imports finish.
        // These estimates are clearly approximate since we can't poll until the server is up.
        setElapsedSeconds((sec) => {
          let calculatedPct = 6;
          if (sec < 30) {
            calculatedPct = 6 + (sec / 30) * 24; // 6% -> 30%
            setSystemStateText("BOOT: LOADING PYTHON RUNTIME & AI MODULES (~60s)...");
          } else if (sec < 60) {
            calculatedPct = 30 + ((sec - 30) / 30) * 15; // 30% -> 45%
            setSystemStateText("IMPORTING AI SERVICES & PYTORCH MODULES...");
          } else if (sec < 90) {
            calculatedPct = 45 + ((sec - 60) / 30) * 5; // 45% -> 50%
            setSystemStateText("STARTING FASTAPI CORE & VOICE ENGINES...");
          } else {
            calculatedPct = Math.min(52, 50 + ((sec - 90) / 30) * 2); // 50% -> 52%
            setSystemStateText("WAITING FOR BACKEND STARTUP TO COMPLETE...");
          }
          currentPct = Math.max(currentPct, Math.round(calculatedPct));
          setProgress(currentPct);
          return sec;
        });'''

assert old in text, 'old block not found!'
text = text.replace(old, new, 1)
with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print('OK')
