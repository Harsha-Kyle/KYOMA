#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <driver/i2s.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <math.h>
#include <WebServer.h>
#include <Preferences.h>

// ================= WiFi & Server Config =================
Preferences preferences;
WebServer cfgServer(80);

// Default credentials — updated automatically via config portal
String saved_ssid     = "YOUR_WIFI_SSID";
String saved_password = "YOUR_WIFI_PASSWORD";
String saved_ws_host  = "192.168.1.100";
const uint16_t ws_port = 8000;
String saved_api_key  = "YOUR_API_KEY";
String full_ws_path   = "/ws/esp32?api_key=YOUR_API_KEY";

bool configPortalMode = false;
unsigned long startWifiAttempt = 0;

// ================= Hardware Pin Mapping =================
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT  64
#define OLED_RESET     -1
#define I2C_SDA         6
#define I2C_SCL         7

#define SPK_BCLK  4
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

void playChime(bool isConnect) {
  I2SMode oldMode = currentI2SMode;
  initI2SSpeaker();

  const int sampleRate = 16000;
  const int bufferSize = 256;
  int16_t buffer[bufferSize * 2];

  if (isConnect) {
    float duration = 0.35f;
    int totalSamples = sampleRate * duration;
    float phase = 0.0f;

    for (int i = 0; i < totalSamples; i += bufferSize) {
      int chunk = min(bufferSize, totalSamples - i);
      for (int s = 0; s < chunk; s++) {
        float progress = (float)(i + s) / totalSamples;
        float freq;
        if (progress < 0.25f) {
          freq = 523.0f + (659.0f - 523.0f) * (progress / 0.25f);
        } else if (progress < 0.6f) {
          freq = 659.0f + (784.0f - 659.0f) * ((progress - 0.25f) / 0.35f);
        } else {
          freq = 784.0f + (1046.0f - 784.0f) * ((progress - 0.6f) / 0.4f);
        }

        float env = 25000.0f;
        if (progress > 0.7f) {
          env = 25000.0f * (1.0f - (progress - 0.7f) / 0.3f);
        }

        float sinVal = sin(phase);
        float triVal = (fabs((phase / M_PI) - 1.0f) * 2.0f) - 1.0f;
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
    float duration = 0.4f;
    int totalSamples = sampleRate * duration;
    float phase = 0.0f;

    for (int i = 0; i < totalSamples; i += bufferSize) {
      int chunk = min(bufferSize, totalSamples - i);
      for (int s = 0; s < chunk; s++) {
        float progress = (float)(i + s) / totalSamples;
        float freq = 600.0f * exp(-1.2f * progress);
        float env = 24000.0f * (1.0f - progress);

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

  if (oldMode == I2S_MODE_MIC) {
    initI2SMic();
  } else if (oldMode == I2S_MODE_SPEAKER) {
    initI2SSpeaker();
  } else {
    uninstallI2S();
  }
}

void playBootSweep() {
  I2SMode oldMode = currentI2SMode;
  initI2SSpeaker();
  const int SR = 16000;
  const int BUF = 256;
  int16_t buf[BUF * 2];
  float duration = 0.85f;
  int total = (int)(SR * duration);
  float phase1 = 0.0f, phase2 = 0.0f, phase3 = 0.0f;
  for (int i = 0; i < total; i += BUF) {
    int chunk = min(BUF, total - i);
    for (int s = 0; s < chunk; s++) {
      float p = (float)(i + s) / total;
      float freqMain  = 150.0f * pow(1046.0f / 150.0f, p);
      float freqFifth = freqMain * 1.498f;
      float freqSub   = 80.0f  * pow(250.0f / 80.0f, p);
      float env;
      if      (p < 0.08f) env = p / 0.08f;
      else if (p < 0.82f) env = 1.0f;
      else                env = (1.0f - p) / 0.18f;
      env *= 21000.0f;
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

void playLogoStab() {
  I2SMode oldMode = currentI2SMode;
  initI2SSpeaker();
  const int SR = 16000;
  const int BUF = 256;
  int16_t buf[BUF * 2];
  float duration = 0.38f;
  int total = (int)(SR * duration);
  float p1 = 0.0f, p2 = 0.0f, p3 = 0.0f;
  for (int i = 0; i < total; i += BUF) {
    int chunk = min(BUF, total - i);
    for (int s = 0; s < chunk; s++) {
      float progress = (float)(i + s) / total;
      float env = exp(-3.5f * progress) * 27000.0f;
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

float easeInOut(float t) {
  t = constrain(t, 0.0f, 1.0f);
  return t < 0.5f ? 4 * t * t * t : 1.0f - pow(-2.0f * t + 2.0f, 3.0f) / 2.0f;
}

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

  wl_status_t wifiStatus = WiFi.status();
  bool isWifiConnected = (wifiStatus == WL_CONNECTED);
  
  extern bool wsStarted;
  bool isServerConnected = wsStarted && (webSocket.isConnected());

  if (currentState != STATE_BOOT) {
    uint8_t* buf = display.getBuffer();
    unsigned long now = millis();

    if (!isWifiConnected) {
      for (int bar = 0; bar < 4; bar++) {
        int startY = random(0, 56);
        int barH = random(3, 8);
        int shift = random(-8, 9);
        
        if (shift != 0) {
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
        }
      }

      int sparks = random(10, 40);
      for (int i = 0; i < sparks; i++) {
        display.drawPixel(random(0, 128), random(0, 64), SSD1306_WHITE);
      }
      for (int i = 0; i < sparks; i++) {
        display.drawPixel(random(0, 128), random(0, 64), SSD1306_BLACK);
      }

    } else if (!isServerConnected) {
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
        
        if (random(0, 2) == 0) {
          display.drawFastHLine(0, random(0, 64), 128, SSD1306_WHITE);
        }
      }
    }
  }

  display.display();
}

void drawFuturisticLogo(float glowVal, int scanLineY, float fadeT = 1.0f) {
  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);

  if (fadeT >= 1.0f) {
    display.setCursor(34, 18);
    display.print("KYOMA");
  } else if (fadeT > 0.0f) {
    display.setCursor(34, 18);
    display.print("KYOMA");
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

  if (glowVal > 0.1f) {
    int padding = (int)(glowVal * 3);
    display.drawRoundRect(28 - padding, 14 - padding,
                          72 + padding * 2, 24 + padding * 2, 3, SSD1306_WHITE);
  }
  if (scanLineY >= 0 && scanLineY < 64) {
    display.drawLine(0, scanLineY, 127, scanLineY, SSD1306_WHITE);
  }
}

void drawWifiStatus(unsigned long elapsed) {
  if (WiFi.status() == WL_CONNECTED) return;
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

  if (elapsed < 800) {
  }
  else if (elapsed < 1800) {
    float t = (float)(elapsed - 800) / 1000.0f;
    int radius = (int)(easeInOut(t) * 12.0f);
    if (radius < 1) radius = 1;
    display.drawCircle(64, 32, radius, SSD1306_WHITE);
  }
  else if (elapsed < 2800) {
    float t = (float)(elapsed - 1800) / 1000.0f;
    int ext = (int)(easeInOut(t) * 30.0f);
    display.drawCircle(64, 32, 12, SSD1306_WHITE);
    display.drawLine(64 - 12, 32, 64 - 12 - ext, 32, SSD1306_WHITE);
    display.drawLine(64 + 12, 32, 64 + 12 + ext, 32, SSD1306_WHITE);
    display.drawLine(64, 32 - 12, 64, 32 - 12 - ext / 2, SSD1306_WHITE);
    display.drawLine(64, 32 + 12, 64, 32 + 12 + ext / 2, SSD1306_WHITE);
  }
  else if (elapsed < 4200) {
    float t = (float)(elapsed - 2800) / 1400.0f;
    int scanY = (int)(t * 64.0f);
    float fadeT = constrain(t * 1.4f, 0.0f, 1.0f);
    drawFuturisticLogo(0.0f, scanY, fadeT);
  }

  else if (elapsed < 7200) {
    float t = (float)(elapsed - 4200) / 3000.0f;
    float glow = (sin(t * PI * 6.0f) + 1.0f) / 2.0f;

    const char* subtitle = "Your AI Companion";
    int subLen = strlen(subtitle);
    int charsToShow = (int)(t * (subLen + 2));
    charsToShow = constrain(charsToShow, 0, subLen);
    display.setTextSize(1);
    display.setCursor(13, 46);
    char subBuf[32];
    strncpy(subBuf, subtitle, charsToShow);
    subBuf[charsToShow] = '\0';
    display.print(subBuf);
    if (charsToShow < subLen && ((elapsed / 400) % 2 == 0)) {
      display.print("_");
    }

    for (int i = 0; i < 6; i++) {
      int px = (20 * i + (elapsed / 15)) % 128;
      int py = (10 * i + (elapsed / 25)) % 40;
      display.drawPixel(px, py, SSD1306_WHITE);
    }

    drawFuturisticLogo(glow, -1, 1.0f);
  }
  else if (elapsed < 8200) {
    float t = (float)(elapsed - 7200) / 1000.0f;
    int offset = (int)(easeInOut(t) * 15.0f);
    display.setTextSize(2);
    display.setCursor(34, 18 - offset);
    display.print("KYOMA");
  }

  drawWifiStatus(elapsed);
  display.display();
}

void updateDisplay() {
  static unsigned long lastFrame  = 0;
  const  unsigned long FRAME_MS   = 33;

  unsigned long now = millis();
  if (now - lastFrame < FRAME_MS) return;
  lastFrame = now;

  if (currentState == STATE_BOOT) {
    static unsigned long audioDelayOffset = 0;
    static bool sweepPlayed = false;
    static bool stabPlayed  = false;

    unsigned long rawElapsed = now - lastStateChange;
    if (rawElapsed < 50) {
      sweepPlayed = false;
      stabPlayed = false;
      audioDelayOffset = 0;
    }

    unsigned long elapsed = (now - audioDelayOffset) - lastStateChange;

    if (elapsed < 8200) {
      if (elapsed == 0 && !sweepPlayed) {
        display.clearDisplay();
        display.display();
        sweepPlayed = true;
        unsigned long beforeSP = millis();
        playBootSweep();
        audioDelayOffset += (millis() - beforeSP);
        elapsed = (millis() - audioDelayOffset) - lastStateChange;
      }
      
      if (elapsed >= 2800 && !stabPlayed) {
        animateBootSequence(2800);
        stabPlayed = true;
        unsigned long beforeST = millis();
        playLogoStab();
        audioDelayOffset += (millis() - beforeST);
        elapsed = (millis() - audioDelayOffset) - lastStateChange;
      }

      animateBootSequence(elapsed);
    } else {
      static bool faceSoundCleared = false;
      if (!faceSoundCleared) {
        uninstallI2S();
        faceSoundCleared = true;
      }

      float faceProgress = (float)(elapsed - 8200) / 3000.0f;
      if (faceProgress >= 1.0f) {
        currentState = STATE_IDLE;
        lastStateChange = now;
        faceSoundCleared = false;
      } else {
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

  static float   blinkT     = 1.0f;
  static int     blinkStage = 0;
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

  if (currentState == STATE_IDLE) {
    float breath = sin((float)now / 2400.0f) * 0.07f;
    a.blinkT    = constrain(blinkT + breath, 0.0f, 1.0f);
    a.pupilX    = (int)(sin((float)now / 3700.0f) * 3.5f);
    a.pupilY    = (int)(cos((float)now / 5100.0f) * 2.0f);
    a.mouthOpen = 0.0f;
    renderFrame(a, false, false);
    return;
  }

  if (currentState == STATE_LISTENING) {
    a.blinkT    = max(blinkT, 0.85f);
    a.pupilX    = 0;
    a.pupilY    = -2;
    float lp    = (sin((float)now / 180.0f) + 1.0f) / 2.0f;
    a.mouthOpen = 0.12f + lp * 0.15f;
    renderFrame(a, false, true);
    return;
  }

  if (currentState == STATE_THINKING) {
    a.blinkT    = min(blinkT, 0.72f);
    a.pupilX    = (int)(sin((float)now / 600.0f) * 4.0f);
    a.pupilY    = -1;
    a.mouthOpen = 0.04f;
    renderFrame(a, true, false);
    return;
  }

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

void loadConfig() {
  preferences.begin("kyoma", true);
  saved_ssid     = preferences.getString("ssid",     saved_ssid);
  saved_password = preferences.getString("password", saved_password);
  saved_ws_host  = preferences.getString("ws_host",  saved_ws_host);
  saved_api_key  = preferences.getString("api_key",  saved_api_key);
  preferences.end();
  full_ws_path = "/ws/esp32?api_key=" + saved_api_key;
  Serial.printf("[Config] SSID=%s Host=%s\n", saved_ssid.c_str(), saved_ws_host.c_str());
}

void startConfigPortal() {
  Serial.println("[Config] Starting AP portal...");
  WiFi.disconnect();
  WiFi.mode(WIFI_AP);
  WiFi.softAP("KYOMA_VOICE_CONFIG");

  cfgServer.on("/", HTTP_GET, []() {
    String html = "<html><head><title>Kyoma Config</title>";
    html += "<meta name='viewport' content='width=device-width,initial-scale=1'>";
    html += "<style>body{font-family:sans-serif;background:#1e1e2e;color:#cdd6f4;padding:20px}";
    html += "input{width:100%;padding:10px;margin:8px 0;border:0;border-radius:4px;box-sizing:border-box}";
    html += "button{background:#89b4fa;color:#11111b;padding:12px 24px;border:0;border-radius:4px;font-weight:bold;width:100%}";
    html += ".card{background:#313244;padding:20px;border-radius:8px;max-width:400px;margin:auto}</style>";
    html += "</head><body><div class='card'><h2>Kyoma Setup</h2><form method='POST' action='/save'>";
    html += "WiFi SSID:<input name='ssid' value='" + saved_ssid + "'>";
    html += "WiFi Password:<input name='password' type='password' value='" + saved_password + "'>";
    html += "Server IP:<input name='ws_host' value='" + saved_ws_host + "'>";
    html += "API Key:<input name='api_key' value='" + saved_api_key + "'>";
    html += "<br><button type='submit'>Save &amp; Reboot</button></form></div></body></html>";
    cfgServer.send(200, "text/html", html);
  });

  cfgServer.on("/save", HTTP_POST, []() {
    preferences.begin("kyoma", false);
    preferences.putString("ssid",     cfgServer.arg("ssid"));
    preferences.putString("password", cfgServer.arg("password"));
    preferences.putString("ws_host",  cfgServer.arg("ws_host"));
    preferences.putString("api_key",  cfgServer.arg("api_key"));
    preferences.end();
    cfgServer.send(200, "text/html", "<html><body><h3>Saved! Rebooting...</h3></body></html>");
    delay(2000);
    ESP.restart();
  });

  cfgServer.begin();
  configPortalMode = true;
  currentState = STATE_IDLE;
  uninstallI2S();
}

bool wifiStarted = false;
bool wsStarted = false;

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== Kyoma VTuber ESP32-C3 Client ===");

  Wire.begin(I2C_SDA, I2C_SCL);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("SSD1306 allocation failed"));
  }

  loadConfig();

  currentState = STATE_BOOT;
  lastStateChange = millis();

  Serial.printf("[WiFi] Connecting to: %s\n", saved_ssid.c_str());
  WiFi.begin(saved_ssid.c_str(), saved_password.c_str());
  startWifiAttempt = millis();
  wifiStarted = true;

  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(3000);
}

void loop() {
  if (configPortalMode) {
    cfgServer.handleClient();
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.drawRoundRect(0, 0, 128, 64, 4, SSD1306_WHITE);
    display.setCursor(8, 8);  display.println("  [ Kyoma Config ]");
    display.drawLine(4, 18, 123, 18, SSD1306_WHITE);
    display.setCursor(6, 24); display.println("Connect to WiFi:");
    display.setCursor(6, 34); display.println("KYOMA_VOICE_CONFIG");
    display.setCursor(6, 46); display.println("Open 192.168.4.1");
    display.display();
    delay(10);
    return;
  }

  if (!wifiStarted || (WiFi.status() != WL_CONNECTED && millis() - startWifiAttempt > 15000 && !wsStarted)) {
    startConfigPortal();
    return;
  }

  updateDisplay();

  if (wsStarted) {
    webSocket.loop();
  }

  if (currentState != STATE_BOOT) {
    static wl_status_t lastWifiStatus = WL_IDLE_STATUS;
    wl_status_t currentWifiStatus = WiFi.status();

    if (currentWifiStatus != lastWifiStatus) {
      if (currentWifiStatus == WL_CONNECTED) {
        Serial.println("\nWiFi Connected chime playing...");
        playChime(true);
        lastStateChange += 350;
      } else if (lastWifiStatus == WL_CONNECTED) {
        Serial.println("\nWiFi Disconnected chime playing...");
        playChime(false);
        lastStateChange += 400;
      }
      lastWifiStatus = currentWifiStatus;
    }

    if (currentWifiStatus == WL_CONNECTED) {
      if (!wsStarted) {
        Serial.print("[WiFi] IP: "); Serial.println(WiFi.localIP());
        Serial.printf("[WS] Connecting to %s:%d%s\n", saved_ws_host.c_str(), ws_port, full_ws_path.c_str());
        webSocket.begin(saved_ws_host.c_str(), ws_port, full_ws_path.c_str());
        wsStarted = true;
      }
    }
  }

  if (currentState == STATE_LISTENING && currentI2SMode == I2S_MODE_MIC) {
    for (int pass = 0; pass < 2; pass++) {
      int32_t raw_samples[256];
      int16_t out_samples[256];
      size_t  bytesRead = 0;

      esp_err_t res = i2s_read(I2S_PORT, raw_samples, sizeof(raw_samples), &bytesRead, 5);
      if (res != ESP_OK || bytesRead == 0) break;

      int samplesRead = bytesRead / sizeof(int32_t);
      for (int i = 0; i < samplesRead; i++) {
        out_samples[i] = (int16_t)(raw_samples[i] >> 14);
      }
      webSocket.sendBIN((uint8_t*)out_samples, samplesRead * sizeof(int16_t));
    }
  }

  delay(2);
}
