#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <driver/i2s.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <math.h>

// ================= WiFi & Server Config =================
const char* ssid     = "OPPO F19 Pro+";
const char* password = "3wtisktj";
const char* ws_host  = "192.168.12.190";
const uint16_t ws_port = 8000;
const char* ws_path  = "/ws/esp32";

// ================= Hardware Pin Mapping =================
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT  64
#define OLED_RESET     -1
#define I2C_SDA         6
#define I2C_SCL         7

#define SPK_BCLK  8
#define SPK_LRC   5
#define SPK_DIN   3

#define MIC_SCK  20
#define MIC_WS   10
#define MIC_SD    2

// ================= Global State =================
enum AIState {
  STATE_BOOT,
  STATE_IDLE,
  STATE_LISTENING,
  STATE_THINKING,
  STATE_SPEAKING
};
AIState currentState = STATE_BOOT;
unsigned long lastStateChange = 0;

WebSocketsClient webSocket;
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

#define SAMPLE_RATE 16000
#define I2S_PORT    I2S_NUM_0

enum I2SMode { I2S_MODE_NONE, I2S_MODE_MIC, I2S_MODE_SPEAKER };
I2SMode currentI2SMode = I2S_MODE_NONE;

void initI2SMic();
void initI2SSpeaker();
void uninstallI2S();

// ================= I2S Dynamic Switching =================
void uninstallI2S() {
  if (currentI2SMode != I2S_MODE_NONE) {
    i2s_driver_uninstall(I2S_PORT);
    currentI2SMode = I2S_MODE_NONE;
    delay(10);
  }
}

void initI2SMic() {
  if (currentI2SMode == I2S_MODE_MIC) return;
  uninstallI2S();
  Serial.println("Configuring I2S for Microphone (INMP441)...");
  i2s_config_t i2s_config = {
    .mode                = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate         = SAMPLE_RATE,
    .bits_per_sample     = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format      = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format= I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags    = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count       = 8,
    .dma_buf_len         = 256,
    .use_apll            = false,
    .tx_desc_auto_clear  = false,
    .fixed_mclk          = 0
  };
  i2s_pin_config_t pin_config = {
    .bck_io_num   = MIC_SCK,
    .ws_io_num    = MIC_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num  = MIC_SD
  };
  esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  if (err != ESP_OK) { Serial.printf("Mic I2S driver install failed: %d\n", err); return; }
  err = i2s_set_pin(I2S_PORT, &pin_config);
  if (err != ESP_OK) { Serial.printf("Mic I2S pin set failed: %d\n", err); return; }
  currentI2SMode = I2S_MODE_MIC;
  Serial.println("Microphone initialized.");
}

void initI2SSpeaker() {
  if (currentI2SMode == I2S_MODE_SPEAKER) return;
  uninstallI2S();
  Serial.println("Configuring I2S for Speaker (MAX98357A)...");
  i2s_config_t i2s_config = {
    .mode                = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
    .sample_rate         = SAMPLE_RATE,
    .bits_per_sample     = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format      = I2S_CHANNEL_FMT_RIGHT_LEFT,
    .communication_format= I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags    = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count       = 8,
    .dma_buf_len         = 256,
    .use_apll            = false,
    .tx_desc_auto_clear  = true,
    .fixed_mclk          = 0
  };
  i2s_pin_config_t pin_config = {
    .bck_io_num   = SPK_BCLK,
    .ws_io_num    = SPK_LRC,
    .data_out_num = SPK_DIN,
    .data_in_num  = I2S_PIN_NO_CHANGE
  };
  esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  if (err != ESP_OK) { Serial.printf("Speaker I2S driver install failed: %d\n", err); return; }
  err = i2s_set_pin(I2S_PORT, &pin_config);
  if (err != ESP_OK) { Serial.printf("Speaker I2S pin set failed: %d\n", err); return; }
  i2s_zero_dma_buffer(I2S_PORT);
  currentI2SMode = I2S_MODE_SPEAKER;
  Serial.println("Speaker initialized.");
}

// Play a clean procedural synth chime (non-blocking in main flow, synchronous play during event)
void playChime(bool isConnect) {
  // Save current I2S mode to restore it afterwards
  I2SMode oldMode = currentI2SMode;
  initI2SSpeaker();

  const int sampleRate = 16000;
  const int bufferSize = 256;
  int16_t buffer[bufferSize * 2]; // Stereo (L+R interleaved)

  if (isConnect) {
    // Connect Chime: Fast sythny arpeggio sweep up (3 notes connected by slides)
    // Plays C5 (523Hz) -> E5 (659Hz) -> G5 (784Hz) -> C6 (1046Hz)
    float duration = 0.35f; // 350ms total
    int totalSamples = sampleRate * duration;
    float phase = 0.0f;

    for (int i = 0; i < totalSamples; i += bufferSize) {
      int chunk = min(bufferSize, totalSamples - i);
      for (int s = 0; s < chunk; s++) {
        float progress = (float)(i + s) / totalSamples;
        
        // Pitch glide arpeggio curve
        float freq;
        if (progress < 0.25f) {
          freq = 523.0f + (659.0f - 523.0f) * (progress / 0.25f);
        } else if (progress < 0.6f) {
          freq = 659.0f + (784.0f - 659.0f) * ((progress - 0.25f) / 0.35f);
        } else {
          freq = 784.0f + (1046.0f - 784.0f) * ((progress - 0.6f) / 0.4f);
        }

        // Amplitude envelope: start quick, fade at the very end
        float env = 25000.0f;
        if (progress > 0.7f) {
          env = 25000.0f * (1.0f - (progress - 0.7f) / 0.3f);
        }

        // Use a blend of sine and triangle wave for a brighter, louder synthy sound
        float sinVal = sin(phase);
        // Triangle wave formula: (abs((phase / pi) - 1) * 2) - 1
        float triVal = (fabs((phase / M_PI) - 1.0f) * 2.0f) - 1.0f;
        // 60% Sine + 40% Triangle
        int16_t sample = (int16_t)((0.6f * sinVal + 0.4f * triVal) * env);

        float phaseIncrement = (2.0f * M_PI * freq) / sampleRate;
        phase += phaseIncrement;
        while (phase >= 2.0f * M_PI) phase -= 2.0f * M_PI;

        buffer[s * 2] = sample;
        buffer[s * 2 + 1] = sample;
      }
      size_t bytesWritten = 0;
      i2s_write(I2S_PORT, buffer, chunk * 4, &bytesWritten, portMAX_DELAY);
    }
  } else {
    // Disconnect Chime: Heavy descending sci-fi warp sweep (600Hz -> 180Hz)
    float duration = 0.4f; // 400ms total
    int totalSamples = sampleRate * duration;
    float phase = 0.0f;

    for (int i = 0; i < totalSamples; i += bufferSize) {
      int chunk = min(bufferSize, totalSamples - i);
      for (int s = 0; s < chunk; s++) {
        float progress = (float)(i + s) / totalSamples;
        
        // Exponential-like frequency slide down
        float freq = 600.0f * exp(-1.2f * progress);
        
        // volume decay
        float env = 24000.0f * (1.0f - progress);

        // Blended wave for a retro robotic power-down sound
        float sinVal = sin(phase);
        float triVal = (fabs((phase / M_PI) - 1.0f) * 2.0f) - 1.0f;
        int16_t sample = (int16_t)((0.5f * sinVal + 0.5f * triVal) * env);

        float phaseIncrement = (2.0f * M_PI * freq) / sampleRate;
        phase += phaseIncrement;
        while (phase >= 2.0f * M_PI) phase -= 2.0f * M_PI;

        buffer[s * 2] = sample;
        buffer[s * 2 + 1] = sample;
      }
      size_t bytesWritten = 0;
      i2s_write(I2S_PORT, buffer, chunk * 4, &bytesWritten, portMAX_DELAY);
    }
  }

  // Restore I2S mode
  if (oldMode == I2S_MODE_MIC) {
    initI2SMic();
  } else if (oldMode == I2S_MODE_SPEAKER) {
    initI2SSpeaker();
  } else {
    uninstallI2S();
  }
}

// ---- Boot Sweep: cinematic 3-layer power-on sweep ----
// Layer 1 (main):  150Hz -> 1046Hz  exponential curve
// Layer 2 (fifth): main * 1.498     perfect fifth harmony
// Layer 3 (sub):   80Hz  -> 250Hz   bass rumble
void playBootSweep() {
  I2SMode oldMode = currentI2SMode;
  initI2SSpeaker();
  const int SR = 16000;
  const int BUF = 256;
  int16_t buf[BUF * 2];
  float duration = 0.85f; // 850ms - longer for drama
  int total = (int)(SR * duration);
  float phase1 = 0.0f, phase2 = 0.0f, phase3 = 0.0f;
  for (int i = 0; i < total; i += BUF) {
    int chunk = min(BUF, total - i);
    for (int s = 0; s < chunk; s++) {
      float p = (float)(i + s) / total;
      // Exponential sweep feels more natural than linear
      float freqMain  = 150.0f * pow(1046.0f / 150.0f, p);
      float freqFifth = freqMain * 1.498f;   // perfect fifth
      float freqSub   = 80.0f  * pow(250.0f / 80.0f, p);
      // Envelope: 8% attack, full sustain, 18% release
      float env;
      if      (p < 0.08f) env = p / 0.08f;
      else if (p < 0.82f) env = 1.0f;
      else                env = (1.0f - p) / 0.18f;
      env *= 21000.0f;
      // Sine+triangle blend for richness
      float sinM = sin(phase1);
      float triM = (fabs((phase1 / M_PI) - 1.0f) * 2.0f) - 1.0f;
      float sinF = sin(phase2);
      float triF = (fabs((phase2 / M_PI) - 1.0f) * 2.0f) - 1.0f;
      float sample = (0.65f * sinM + 0.35f * triM) * 0.60f
                   + (0.65f * sinF + 0.35f * triF) * 0.25f
                   + sin(phase3)                    * 0.15f;
      int16_t out = (int16_t)(sample * env);
      phase1 += (2.0f * M_PI * freqMain)  / SR;
      phase2 += (2.0f * M_PI * freqFifth) / SR;
      phase3 += (2.0f * M_PI * freqSub)   / SR;
      while (phase1 >= 2.0f * M_PI) phase1 -= 2.0f * M_PI;
      while (phase2 >= 2.0f * M_PI) phase2 -= 2.0f * M_PI;
      while (phase3 >= 2.0f * M_PI) phase3 -= 2.0f * M_PI;
      buf[s * 2] = out; buf[s * 2 + 1] = out;
    }
    size_t bw = 0;
    i2s_write(I2S_PORT, buf, chunk * 4, &bw, portMAX_DELAY);
  }
  if (oldMode == I2S_MODE_MIC)       initI2SMic();
  else if (oldMode == I2S_MODE_NONE) uninstallI2S();
}

// ---- Logo Stab: C major triad chord hit (C6 + E6 + G6) with ring-out ----
void playLogoStab() {
  I2SMode oldMode = currentI2SMode;
  initI2SSpeaker();
  const int SR = 16000;
  const int BUF = 256;
  int16_t buf[BUF * 2];
  float duration = 0.38f; // 380ms - let the chord ring
  int total = (int)(SR * duration);
  float p1 = 0.0f, p2 = 0.0f, p3 = 0.0f;
  for (int i = 0; i < total; i += BUF) {
    int chunk = min(BUF, total - i);
    for (int s = 0; s < chunk; s++) {
      float progress = (float)(i + s) / total;
      // Hard attack, exponential decay ring-out
      float env = exp(-3.5f * progress) * 27000.0f;
      // C major triad: C6=1047Hz, E6=1319Hz, G6=1568Hz
      float s1 = sin(p1);
      float s2 = sin(p2) * 0.75f;
      float s3 = sin(p3) * 0.55f;
      int16_t sample = (int16_t)((s1 + s2 + s3) / 2.3f * env);
      p1 += (2.0f * M_PI * 1047.0f) / SR;
      p2 += (2.0f * M_PI * 1319.0f) / SR;
      p3 += (2.0f * M_PI * 1568.0f) / SR;
      while (p1 >= 2.0f * M_PI) p1 -= 2.0f * M_PI;
      while (p2 >= 2.0f * M_PI) p2 -= 2.0f * M_PI;
      while (p3 >= 2.0f * M_PI) p3 -= 2.0f * M_PI;
      buf[s * 2] = sample; buf[s * 2 + 1] = sample;
    }
    size_t bw = 0;
    i2s_write(I2S_PORT, buf, chunk * 4, &bw, portMAX_DELAY);
  }
  if (oldMode == I2S_MODE_MIC)       initI2SMic();
  else if (oldMode == I2S_MODE_NONE) uninstallI2S();
}

// ---- Eye-open Whoosh: detuned dual-layer shimmer upswep ----
void playEyeOpenWhoosh() {
  I2SMode oldMode = currentI2SMode;
  initI2SSpeaker();
  const int SR = 16000;
  const int BUF = 256;
  int16_t buf[BUF * 2];
  float duration = 0.42f; // 420ms
  int total = (int)(SR * duration);
  float ph1 = 0.0f, ph2 = 0.0f;
  for (int i = 0; i < total; i += BUF) {
    int chunk = min(BUF, total - i);
    for (int s = 0; s < chunk; s++) {
      float progress = (float)(i + s) / total;
      // Main sweep: 200Hz -> 1320Hz
      float freqMain    = 200.0f + (1320.0f - 200.0f) * progress;
      // Slightly detuned layer for shimmer/chorus width
      float freqShimmer = freqMain * 1.008f;
      // ADSR: 20% attack, sustain to 70%, 30% release
      float env;
      if      (progress < 0.20f) env = progress / 0.20f;
      else if (progress < 0.70f) env = 1.0f;
      else                       env = (1.0f - progress) / 0.30f;
      env *= 14500.0f;
      float sample = sin(ph1) * 0.6f + sin(ph2) * 0.4f;
      int16_t out = (int16_t)(sample * env);
      ph1 += (2.0f * M_PI * freqMain)    / SR;
      ph2 += (2.0f * M_PI * freqShimmer) / SR;
      while (ph1 >= 2.0f * M_PI) ph1 -= 2.0f * M_PI;
      while (ph2 >= 2.0f * M_PI) ph2 -= 2.0f * M_PI;
      buf[s * 2] = out; buf[s * 2 + 1] = out;
    }
    size_t bw = 0;
    i2s_write(I2S_PORT, buf, chunk * 4, &bw, portMAX_DELAY);
  }
  if (oldMode == I2S_MODE_MIC)       initI2SMic();
  else if (oldMode == I2S_MODE_NONE) uninstallI2S();
}




// Smooth easing: ease-in-out cubic

float easeInOut(float t) {
  t = constrain(t, 0.0f, 1.0f);
  return t < 0.5f ? 4 * t * t * t : 1.0f - pow(-2.0f * t + 2.0f, 3.0f) / 2.0f;
}

// Draw one capsule eye with pupil + glint
void drawSingleEye(int cx, int cy, int eyeW, int fullH, float blinkT,
                   int pupilOffX, int pupilOffY) {
  int h = (int)(fullH * blinkT);
  if (h < 2) {
    display.fillRoundRect(cx - eyeW / 2, cy - 1, eyeW, 3, 1, SSD1306_WHITE);
    return;
  }
  display.fillRoundRect(cx - eyeW / 2, cy - h / 2, eyeW, h, eyeW / 2, SSD1306_WHITE);
  int pRadius = max(2, (int)(h / 3.5f));
  int px = cx + pupilOffX;
  int py = cy + pupilOffY;
  display.fillCircle(px, py, pRadius, SSD1306_BLACK);
  int gRadius = max(1, pRadius / 2);
  display.fillCircle(px - gRadius, py - gRadius, gRadius, SSD1306_WHITE);
}

// Draw capsule mouth
void drawMouth(int cx, int cy, float openT) {
  openT = constrain(openT, 0.0f, 1.0f);
  if (openT < 0.05f) {
    display.fillRoundRect(cx - 7, cy,     3, 2, 1, SSD1306_WHITE);
    display.fillRoundRect(cx - 2, cy + 2, 6, 2, 1, SSD1306_WHITE);
    display.fillRoundRect(cx + 5, cy,     3, 2, 1, SSD1306_WHITE);
    return;
  }
  int mouthW = (int)(10 + openT * 14);
  int mouthH = (int)(4  + openT * 10);
  int r = mouthH / 2;
  display.fillRoundRect(cx - mouthW / 2, cy - mouthH / 2, mouthW, mouthH, r, SSD1306_WHITE);
  if (mouthH > 6) {
    int iW = mouthW - 4;
    int iH = mouthH - 4;
    int ir = iH / 2;
    display.fillRoundRect(cx - iW / 2, cy - iH / 2, iW, iH, ir, SSD1306_BLACK);
  }
}

// ================= Core Renderer =================
struct EyeAnim {
  float blinkT    = 1.0f;
  int   pupilX    = 0;
  int   pupilY    = 0;
  float mouthOpen = 0.0f;
};

void renderFrame(const EyeAnim& a, bool thinkingDots, bool listenRing) {
  display.clearDisplay();

  const int leftCX  = 35;
  const int rightCX = 93;
  const int eyeCY   = 26;
  const int eyeW    = 24;
  const int eyeH    = 20;

  drawSingleEye(leftCX,  eyeCY, eyeW, eyeH, a.blinkT, a.pupilX, a.pupilY);
  drawSingleEye(rightCX, eyeCY, eyeW, eyeH, a.blinkT, a.pupilX, a.pupilY);

  int mCX = 64, mCY = 52;
  drawMouth(mCX, mCY, a.mouthOpen);

  if (thinkingDots) {
    float angle = (float)millis() / 300.0f;
    int r = 7, cx = 64, cy = 8;
    display.fillCircle(cx + (int)(cos(angle)       * r), cy + (int)(sin(angle)       * r), 2, SSD1306_WHITE);
    display.fillCircle(cx + (int)(cos(angle + 2.1f) * r), cy + (int)(sin(angle + 2.1f) * r), 2, SSD1306_WHITE);
    display.fillCircle(cx + (int)(cos(angle + 4.2f) * r), cy + (int)(sin(angle + 4.2f) * r), 1, SSD1306_WHITE);
  }

  if (listenRing) {
    float pulse = (sin((float)millis() / 200.0f) + 1.0f) / 2.0f;
    int pr = (int)(3 + pulse * 5);
    display.drawCircle(mCX, mCY, pr + 6, SSD1306_WHITE);
  }

  // ---- Glitch effect logic for WiFi / server disconnect ----
  wl_status_t wifiStatus = WiFi.status();
  bool isWifiConnected = (wifiStatus == WL_CONNECTED);
  
  // extern wsStarted from main loop context to check server WebSocket status
  extern bool wsStarted;
  bool isServerConnected = wsStarted && (webSocket.isConnected());

  // Only apply glitch after the boot sequence is complete
  if (currentState != STATE_BOOT) {
    uint8_t* buf = display.getBuffer();
    unsigned long now = millis();

    if (!isWifiConnected) {
      // 1. SEVERE GLITCH (WiFi Disconnected): Constant heavy horizontal displacement + noise
      // Shift random horizontal blocks
      for (int bar = 0; bar < 4; bar++) {
        int startY = random(0, 56);
        int barH = random(3, 8);
        int shift = random(-8, 9); // shift left or right
        
        if (shift != 0) {
          for (int y = startY; y < startY + barH; y++) {
            // Horizontal shift inside SSD1306 buffer: 128px wide is 16 bytes per row
            uint8_t tempRow[16];
            memcpy(tempRow, &buf[y * 16], 16);
            memset(&buf[y * 16], 0, 16);
            
            for (int col = 0; col < 128; col++) {
              int srcCol = (col - shift + 128) % 128;
              int srcByte = srcCol / 8;
              int srcBit = 7 - (srcCol % 8);
              
              if (tempRow[srcByte] & (1 << srcBit)) {
                int destByte = col / 8;
                int destBit = 7 - (col % 8);
                buf[y * 16 + destByte] |= (1 << destBit);
              }
            }
          }
        }
      }

      // Add white/black noise sparks
      int sparks = random(10, 40);
      for (int i = 0; i < sparks; i++) {
        display.drawPixel(random(0, 128), random(0, 64), SSD1306_WHITE);
      }
      for (int i = 0; i < sparks; i++) {
        display.drawPixel(random(0, 128), random(0, 64), SSD1306_BLACK);
      }

    } else if (!isServerConnected) {
      // 2. SUBTLE/PERIODIC TWITCH (Server Disconnected but WiFi OK)
      // Occurs briefly every 2-3 seconds
      if ((now % 3000) < 150) {
        int shift = random(-3, 4);
        int startY = random(10, 45);
        int barH = random(5, 12);
        
        for (int y = startY; y < startY + barH; y++) {
          uint8_t tempRow[16];
          memcpy(tempRow, &buf[y * 16], 16);
          memset(&buf[y * 16], 0, 16);
          
          for (int col = 0; col < 128; col++) {
            int srcCol = (col - shift + 128) % 128;
            int srcByte = srcCol / 8;
            int srcBit = 7 - (srcCol % 8);
            
            if (tempRow[srcByte] & (1 << srcBit)) {
              int destByte = col / 8;
              int destBit = 7 - (col % 8);
              buf[y * 16 + destByte] |= (1 << destBit);
            }
          }
        }
        
        // Faint flicker lines
        if (random(0, 2) == 0) {
          display.drawFastHLine(0, random(0, 64), 128, SSD1306_WHITE);
        }
      }
    }
  }

  display.display();
}

// ================= Cinematic Boot Sequence =================

// Improvement 5: Draw logo with dither fade (fadeT 0=invisible, 1=full)
void drawFuturisticLogo(float glowVal, int scanLineY, float fadeT = 1.0f) {
  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);

  if (fadeT >= 1.0f) {
    // Full brightness
    display.setCursor(34, 18);
    display.print("KYOMA");
  } else if (fadeT > 0.0f) {
    // Dithered fade: draw logo into a temp buffer then mask by checkerboard density
    // We draw into display normally, then erase pixels based on dither threshold.
    display.setCursor(34, 18);
    display.print("KYOMA");
    // Determine dither pattern: 4 levels
    // fadeT < 0.25 -> keep only 1/4 pixels (every other col AND row)
    // fadeT < 0.50 -> keep 1/2 pixels (every other col)
    // fadeT < 0.75 -> keep 3/4 pixels (erase only every 4th col)
    // fadeT >= 1.0 -> full
    uint8_t* b = display.getBuffer();
    for (int y = 14; y < 42; y++) {
      for (int x = 28; x < 100; x++) {
        bool keep;
        if      (fadeT < 0.25f) keep = ((x % 2 == 0) && (y % 2 == 0));
        else if (fadeT < 0.5f)  keep = (x % 2 == 0);
        else if (fadeT < 0.75f) keep = !(x % 4 == 0 && y % 2 == 0);
        else                    keep = true;
        if (!keep) {
          int byte_idx = y * 16 + x / 8;
          int bit_pos  = 7 - (x % 8);
          b[byte_idx] &= ~(1 << bit_pos);
        }
      }
    }
  }
  // else fadeT==0: don't draw text at all

  if (glowVal > 0.1f) {
    int padding = (int)(glowVal * 3);
    display.drawRoundRect(28 - padding, 14 - padding,
                          72 + padding * 2, 24 + padding * 2, 3, SSD1306_WHITE);
  }
  if (scanLineY >= 0 && scanLineY < 64) {
    display.drawLine(0, scanLineY, 127, scanLineY, SSD1306_WHITE);
  }
}

// Improvement 4: WiFi status dots drawn in bottom-right corner
void drawWifiStatus(unsigned long elapsed) {
  if (WiFi.status() == WL_CONNECTED) return; // hide once connected
  // 3 dots that pulse in sequence
  int dotX[3] = {110, 117, 124};
  int dotY = 58;
  int dotIdx = (elapsed / 400) % 3;
  for (int d = 0; d < 3; d++) {
    if (d <= dotIdx) {
      display.fillCircle(dotX[d], dotY, 2, SSD1306_WHITE);
    } else {
      display.drawCircle(dotX[d], dotY, 2, SSD1306_WHITE);
    }
  }
}


void animateBootSequence(unsigned long elapsed) {
  display.clearDisplay();

  // Duration milestones (Total logo sequence: 8200 ms)
  // Stage 1: 0    - 800ms  : Black screen
  // Stage 2: 800  - 1800ms : Pixel expands to circle  [sweep sound played via caller]
  // Stage 3: 1800 - 2800ms : Circuit lines
  // Stage 4: 2800 - 4200ms : Logo dither fade-in + scanline  [stab sound played via caller]
  // Stage 5: 4200 - 7200ms : Subtitle typewriter + particles + glow
  // Stage 6: 7200 - 8200ms : Logo slides away

  if (elapsed < 800) {
    // Stage 1: Black
  }
  else if (elapsed < 1800) {
    // Stage 2: circle expands
    float t = (float)(elapsed - 800) / 1000.0f;
    int radius = (int)(easeInOut(t) * 12.0f);
    if (radius < 1) radius = 1;
    display.drawCircle(64, 32, radius, SSD1306_WHITE);
  }
  else if (elapsed < 2800) {
    // Stage 3: Circuit lines
    float t = (float)(elapsed - 1800) / 1000.0f;
    int ext = (int)(easeInOut(t) * 30.0f);
    display.drawCircle(64, 32, 12, SSD1306_WHITE);
    display.drawLine(64 - 12, 32, 64 - 12 - ext, 32, SSD1306_WHITE);
    display.drawLine(64 + 12, 32, 64 + 12 + ext, 32, SSD1306_WHITE);
    display.drawLine(64, 32 - 12, 64, 32 - 12 - ext / 2, SSD1306_WHITE);
    display.drawLine(64, 32 + 12, 64, 32 + 12 + ext / 2, SSD1306_WHITE);
  }
  else if (elapsed < 4200) {
    // Stage 4: Logo dither fade-in with scanline
    float t = (float)(elapsed - 2800) / 1400.0f;
    int scanY = (int)(t * 64.0f);
    // Improvement 5: dithered fade (t drives density 0->1)
    float fadeT = constrain(t * 1.4f, 0.0f, 1.0f); // slightly faster than scanline
    drawFuturisticLogo(0.0f, scanY, fadeT);
  }

  else if (elapsed < 7200) {
    // Stage 5: glow + typewriter subtitle + particles
    float t = (float)(elapsed - 4200) / 3000.0f;
    float glow = (sin(t * PI * 6.0f) + 1.0f) / 2.0f;

    // Improvement 2: Typewriter subtitle
    const char* subtitle = "Your AI Companion";
    int subLen = strlen(subtitle);
    int charsToShow = (int)(t * (subLen + 2)); // +2 gives a pause at end
    charsToShow = constrain(charsToShow, 0, subLen);
    display.setTextSize(1);
    display.setCursor(13, 46);
    char subBuf[32];
    strncpy(subBuf, subtitle, charsToShow);
    subBuf[charsToShow] = '\0';
    display.print(subBuf);
    // Blinking cursor after last character
    if (charsToShow < subLen && ((elapsed / 400) % 2 == 0)) {
      display.print("_");
    }

    // Drifting particles
    for (int i = 0; i < 6; i++) {
      int px = (20 * i + (elapsed / 15)) % 128;
      int py = (10 * i + (elapsed / 25)) % 40;
      display.drawPixel(px, py, SSD1306_WHITE);
    }

    drawFuturisticLogo(glow, -1, 1.0f);
  }
  else if (elapsed < 8200) {
    // Stage 6: slide away
    float t = (float)(elapsed - 7200) / 1000.0f;
    int offset = (int)(easeInOut(t) * 15.0f);
    display.setTextSize(2);
    display.setCursor(34, 18 - offset);
    display.print("KYOMA");
  }

  // Improvement 4: WiFi dots always visible during boot
  drawWifiStatus(elapsed);

  display.display();
}


// ================= updateDisplay =================
void updateDisplay() {
  static unsigned long lastFrame  = 0;
  const  unsigned long FRAME_MS   = 33; // ~30 FPS

  unsigned long now = millis();
  if (now - lastFrame < FRAME_MS) return;
  lastFrame = now;

  // ---------- BOOT STATE ANIMATION ----------
  if (currentState == STATE_BOOT) {
    // Offset the timer by the duration of audio segments played, 
    // so the video resumes exactly where it paused during audio play.
    static unsigned long audioDelayOffset = 0;
    
    // Trigger trackers
    static bool sweepPlayed = false;
    static bool stabPlayed  = false;
    static bool whooshPlayed = false;

    // Reset trackers if it is a fresh boot state
    unsigned long rawElapsed = now - lastStateChange;
    if (rawElapsed < 50) {
      sweepPlayed = false;
      stabPlayed = false;
      whooshPlayed = false;
      audioDelayOffset = 0;
    }

    // Determine the active elapsed time adjusted for the blocking sound playtimes
    unsigned long elapsed = (now - audioDelayOffset) - lastStateChange;

    // 8200 ms logo sequence + 3000 ms face entrance sequence
    if (elapsed < 8200) {
      // 1. Play the Boot Sweep immediately at the start (on black screen)
      if (elapsed == 0 && !sweepPlayed) {
        // Render a blank black screen first
        display.clearDisplay();
        display.display();
        sweepPlayed = true;
        unsigned long beforeSP = millis();
        playBootSweep(); // 850 ms blocking sound on black screen
        audioDelayOffset += (millis() - beforeSP);
        elapsed = (millis() - audioDelayOffset) - lastStateChange;
      }
      
      // 2. Play the Logo Stab at the milestone (around 2800ms, start of Stage 4)
      if (elapsed >= 2800 && !stabPlayed) {
        // Draw the exact frame just before the sound, so it freezes there!
        animateBootSequence(2800);
        stabPlayed = true;
        unsigned long beforeST = millis();
        playLogoStab(); // 380 ms blocking sound
        audioDelayOffset += (millis() - beforeST);
        elapsed = (millis() - audioDelayOffset) - lastStateChange;
      }

      // Draw the normal animation frame
      animateBootSequence(elapsed);
    } else {
      // Clear sounds / uninstall I2S once when face starts to ensure absolute silence
      static bool faceSoundCleared = false;
      if (!faceSoundCleared) {
        uninstallI2S();
        faceSoundCleared = true;
      }

      float faceProgress = (float)(elapsed - 8200) / 3000.0f;
      if (faceProgress >= 1.0f) {
        currentState = STATE_IDLE;
        lastStateChange = now;
        faceSoundCleared = false; // Reset for next boot if needed
      } else {
        // Face entrance animation:
        // 0.0-0.4 closed, 0.4-0.7 open (NO WHOOSH sound), 0.7-0.9 blink, 0.9-1.0 smile
        EyeAnim a;
        a.pupilX = 0;
        a.pupilY = 0;


        if (faceProgress < 0.4f) {
          a.blinkT = 0.0f;
          a.mouthOpen = 0.0f;
        } else if (faceProgress < 0.7f) {
          float openT = (faceProgress - 0.4f) / 0.3f;
          a.blinkT = easeInOut(openT);
          a.mouthOpen = 0.0f;
        } else if (faceProgress < 0.9f) {
          float blinkPhase = (faceProgress - 0.7f) / 0.2f;
          a.blinkT = blinkPhase < 0.5f
            ? easeInOut(1.0f - (blinkPhase * 2.0f))
            : easeInOut((blinkPhase - 0.5f) * 2.0f);
          a.mouthOpen = 0.0f;
        } else {
          a.blinkT = 1.0f;
          float smileProgress = (faceProgress - 0.9f) / 0.1f;
          a.mouthOpen = easeInOut(smileProgress) * 0.08f;
        }
        renderFrame(a, false, false);
      }
    }
    return;
  }


  // ---------- Smooth blink ----------
  static float   blinkT     = 1.0f;
  static int     blinkStage = 0;     // 0=open, 1=closing, 2=closed, 3=opening
  static int     blinkStep  = 0;
  static unsigned long blinkTimer = 0;
  static unsigned long blinkNext  = 4000;
  const  int     BLINK_STEPS = 5;
  const  unsigned long BLINK_STEP_MS = 40;

  if (blinkStage == 0 && now > blinkNext) {
    blinkStage = 1; blinkStep = 0; blinkTimer = now;
  }
  if (blinkStage == 1 && now - blinkTimer > BLINK_STEP_MS) {
    blinkStep++;
    blinkT = easeInOut(1.0f - (float)blinkStep / BLINK_STEPS);
    blinkTimer = now;
    if (blinkStep >= BLINK_STEPS) { blinkStage = 2; blinkT = 0.0f; blinkTimer = now; }
  } else if (blinkStage == 2 && now - blinkTimer > 60) {
    blinkStage = 3; blinkStep = 0; blinkTimer = now;
  } else if (blinkStage == 3 && now - blinkTimer > BLINK_STEP_MS) {
    blinkStep++;
    blinkT = easeInOut((float)blinkStep / BLINK_STEPS);
    blinkTimer = now;
    if (blinkStep >= BLINK_STEPS) {
      blinkStage = 0; blinkT = 1.0f;
      blinkNext = now + random(3000, 7000);
    }
  }

  EyeAnim a;
  a.blinkT = blinkT;

  // ---------- IDLE ----------
  if (currentState == STATE_IDLE) {
    float breath = sin((float)now / 2400.0f) * 0.07f;
    a.blinkT    = constrain(blinkT + breath, 0.0f, 1.0f);
    a.pupilX    = (int)(sin((float)now / 3700.0f) * 3.5f);
    a.pupilY    = (int)(cos((float)now / 5100.0f) * 2.0f);
    a.mouthOpen = 0.0f;
    renderFrame(a, false, false);
    return;
  }

  // ---------- LISTENING ----------
  if (currentState == STATE_LISTENING) {
    a.blinkT    = max(blinkT, 0.85f);
    a.pupilX    = 0;
    a.pupilY    = -2;
    float lp    = (sin((float)now / 180.0f) + 1.0f) / 2.0f;
    a.mouthOpen = 0.12f + lp * 0.15f;
    renderFrame(a, false, true);
    return;
  }

  // ---------- THINKING ----------
  if (currentState == STATE_THINKING) {
    a.blinkT    = min(blinkT, 0.72f);
    a.pupilX    = (int)(sin((float)now / 600.0f) * 4.0f);
    a.pupilY    = -1;
    a.mouthOpen = 0.04f;
    renderFrame(a, true, false);
    return;
  }

  // ---------- SPEAKING ----------
  if (currentState == STATE_SPEAKING) {
    a.blinkT    = blinkT;
    a.pupilX    = (int)(sin((float)now / 400.0f) * 2.0f);
    a.pupilY    = (int)(cos((float)now / 120.0f) * 2.0f);
    float raw   = (sin((float)now / 90.0f) + 1.0f) / 2.0f;
    float shaped = pow(raw, 0.55f);
    a.mouthOpen  = 0.15f + shaped * 0.85f;
    renderFrame(a, false, false);
    return;
  }
}

// ================= WebSocket Event Handler =================
void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      Serial.println("[WS] Disconnected!");
      currentState = STATE_IDLE;
      lastStateChange = millis();
      break;

    case WStype_CONNECTED:
      Serial.printf("[WS] Connected to url: %s\n", payload);
      if (currentState != STATE_BOOT) {
        currentState = STATE_IDLE;
        lastStateChange = millis();
      }
      initI2SMic();
      break;

    case WStype_TEXT:
      {
        String text = String((char*)payload);
        Serial.printf("[WS] Received text: %s\n", text.c_str());
        if (text.startsWith("state:")) {
          String stateStr = text.substring(6);
          if (currentState != STATE_BOOT) {
            lastStateChange = millis();
            if      (stateStr == "idle")      { currentState = STATE_IDLE;      initI2SMic(); }
            else if (stateStr == "listening") { currentState = STATE_LISTENING; initI2SMic(); }
            else if (stateStr == "thinking")  { currentState = STATE_THINKING;  uninstallI2S(); }
            else if (stateStr == "speaking")  { currentState = STATE_SPEAKING;  initI2SSpeaker(); }
          }
        }
      }
      break;

    case WStype_BIN:
      if (currentState == STATE_SPEAKING) {
        initI2SSpeaker();
        size_t bytesWritten = 0;
        i2s_write(I2S_PORT, payload, length, &bytesWritten, portMAX_DELAY);
      }
      break;

    default:
      break;
  }
}

// ================= Boot Screen Helper =================
void showBootScreen(const char* line1, const char* line2 = nullptr) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.drawRoundRect(0, 0, 128, 64, 4, SSD1306_WHITE);
  display.setCursor(10, 10);
  display.println("  [ Kyoma AI ]");
  display.drawLine(4, 20, 123, 20, SSD1306_WHITE);
  display.setCursor(10, 28);
  display.println(line1);
  if (line2) { display.setCursor(10, 42); display.println(line2); }
  display.display();
}

// ================= Setup & Main Loop =================
bool wifiStarted = false;
bool wsStarted = false;

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== Kyoma VTuber ESP32-C3 Client ===");

  Wire.begin(I2C_SDA, I2C_SCL);
  bool hasDisplay = true;
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("SSD1306 allocation failed"));
    hasDisplay = false;
  }

  // Set state to BOOT immediately so the animation plays first
  currentState = STATE_BOOT;
  lastStateChange = millis();

  // Start WiFi non-blockingly
  Serial.println("Starting WiFi connection...");
  WiFi.begin(ssid, password);
  wifiStarted = true;

  // Configure WebSocket properties (we will begin the connection in loop)
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(3000);
}

void loop() {
  // Update animations/boot screens
  updateDisplay();

  // Run websocket loop if connected/started
  if (wsStarted) {
    webSocket.loop();
  }

  // Once the boot sequence is finished, handle connections and play chimes
  if (currentState != STATE_BOOT) {
    static wl_status_t lastWifiStatus = WL_IDLE_STATUS;
    wl_status_t currentWifiStatus = WiFi.status();

    if (currentWifiStatus != lastWifiStatus) {
      if (currentWifiStatus == WL_CONNECTED) {
        Serial.println("\nWiFi Connected chime playing...");
        playChime(true); // Play bubble chirp connection chime (takes 350ms)
        // Offset lastStateChange so the active face animations don't freeze/jump
        lastStateChange += 350;
      } else if (lastWifiStatus == WL_CONNECTED) {
        Serial.println("\nWiFi Disconnected chime playing...");
        playChime(false); // Play alert decline disconnection chime (takes 400ms)
        lastStateChange += 400;
      }
      lastWifiStatus = currentWifiStatus;
    }

    // 1. Check if WiFi has successfully connected
    if (currentWifiStatus == WL_CONNECTED) {
      // 2. Start WebSocket if it hasn't been started yet
      if (!wsStarted) {
        Serial.print("IP: "); Serial.println(WiFi.localIP());
        Serial.println("Starting WebSocket connection...");
        webSocket.begin(ws_host, ws_port, ws_path);
        wsStarted = true;
      }
    }
  }



  // ---- Mic streaming in LISTENING mode ----
  if (currentState == STATE_LISTENING && currentI2SMode == I2S_MODE_MIC) {
    // Drain up to 2 chunks per loop() call.
    // 256 samples × 4 bytes = 1024 bytes read, 256 × 2 = 512 bytes sent per pass.
    // Keeps each WS binary frame well under the library's ~4 KB TX buffer.
    for (int pass = 0; pass < 2; pass++) {
      int32_t raw_samples[256];
      int16_t out_samples[256];
      size_t  bytesRead = 0;

      esp_err_t res = i2s_read(I2S_PORT, raw_samples, sizeof(raw_samples), &bytesRead, 5);
      if (res != ESP_OK || bytesRead == 0) break;

      int samplesRead = bytesRead / sizeof(int32_t);
      for (int i = 0; i < samplesRead; i++) {
        // INMP441: 24-bit audio packed in the top bits of a 32-bit frame.
        // Right-shift by 14 to preserve full dynamic range as 16-bit.
        out_samples[i] = (int16_t)(raw_samples[i] >> 14);
      }
      webSocket.sendBIN((uint8_t*)out_samples, samplesRead * sizeof(int16_t));
    }
  }

  delay(2);
}
