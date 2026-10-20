// ============================================================
// KYOMA - Creative Happy Birthday Show Firmware
// Features: Party hat, Cake + flickering flame, Fireworks/Confetti,
// Dynamic Expressions, Rhythm Head Bobbing, Candle Blowout Finale!
// ============================================================

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <driver/i2s.h>
#include <math.h>

// ---- Pin Mapping ----
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT  64
#define OLED_RESET     -1
#define I2C_SDA         6
#define I2C_SCL         7

#define SPK_BCLK   4   // D2 / GPIO4
#define SPK_LRC    5
#define SPK_DIN    3

#define I2S_PORT   I2S_NUM_0
#define SAMPLE_RATE 16000

// ---- OLED ----
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// ---- Note Frequencies (Hz) ----
#define C4  262
#define D4  294
#define E4  330
#define F4  349
#define G4  392
#define A4  440
#define Bb4 466
#define B4  494
#define C5  523
#define D5  587
#define E5  659
#define F5  698
#define G5  784
#define A5  880
#define REST 0

struct Note { int freq; int dur; };

const Note happyBirthday[] = {
  // "Hap-py birth-day to you"
  {C4, 280}, {C4, 140}, {D4, 440}, {C4, 440}, {F4, 440}, {E4, 850},
  // "Hap-py birth-day to you"
  {C4, 280}, {C4, 140}, {D4, 440}, {C4, 440}, {G4, 440}, {F4, 850},
  // "Hap-py birth-day dear Kyoma"
  {C4, 280}, {C4, 140}, {C5, 440}, {A4, 440}, {F4, 440}, {E4, 440}, {D4, 850},
  // "Hap-py birth-day to you"
  {Bb4,280}, {Bb4,140}, {A4, 440}, {F4, 440}, {G4, 440}, {F4, 1100},
  {REST, 400}
};
const int NOTE_COUNT = sizeof(happyBirthday) / sizeof(Note);

// Confetti particle system
struct Particle {
  float x, y;
  float vx, vy;
  int size;
};
Particle confetti[12];

void initConfetti() {
  for (int i = 0; i < 12; i++) {
    confetti[i].x = random(0, 128);
    confetti[i].y = random(-20, 0);
    confetti[i].vx = (random(-10, 10) / 10.0f);
    confetti[i].vy = (random(8, 20) / 10.0f);
    confetti[i].size = random(1, 3);
  }
}

void updateConfetti() {
  for (int i = 0; i < 12; i++) {
    confetti[i].x += confetti[i].vx;
    confetti[i].y += confetti[i].vy;
    if (confetti[i].y > 64) {
      confetti[i].y = random(-10, 0);
      confetti[i].x = random(0, 128);
    }
    if (confetti[i].size == 1) {
      display.drawPixel((int)confetti[i].x, (int)confetti[i].y, SSD1306_WHITE);
    } else {
      display.fillRect((int)confetti[i].x, (int)confetti[i].y, confetti[i].size, confetti[i].size, SSD1306_WHITE);
    }
  }
}

// I2S Speaker Setup
void initSpeaker() {
  i2s_config_t cfg = {
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
  i2s_pin_config_t pins = {
    .bck_io_num   = SPK_BCLK,
    .ws_io_num    = SPK_LRC,
    .data_out_num = SPK_DIN,
    .data_in_num  = I2S_PIN_NO_CHANGE
  };
  i2s_driver_install(I2S_PORT, &cfg, 0, NULL);
  i2s_set_pin(I2S_PORT, &pins);
  i2s_zero_dma_buffer(I2S_PORT);
}

void playNote(int freq, int dur) {
  const int BUF = 256;
  int16_t buf[BUF * 2];
  int totalSamples = (SAMPLE_RATE * dur) / 1000;
  float phase = 0.0f;

  for (int i = 0; i < totalSamples; i += BUF) {
    int chunk = min(BUF, totalSamples - i);
    for (int s = 0; s < chunk; s++) {
      float progress = (float)(i + s) / totalSamples;
      float env;
      if      (progress < 0.08f) env = progress / 0.08f;
      else if (progress < 0.75f) env = 1.0f;
      else                       env = (1.0f - progress) / 0.25f;
      env *= 31500.0f; // Max volume for 16-bit audio

      // Rich blend of Sine + Square/Triangle wave for maximum volume & punch
      float sinV = sin(phase);
      float triV = (phase < M_PI) ? 1.0f : -1.0f; // Square wave for high loudness
      int16_t sample = (freq == REST) ? 0 : (int16_t)((0.5f * sinV + 0.5f * triV) * env);

      buf[s * 2]     = sample;
      buf[s * 2 + 1] = sample;

      if (freq != REST) {
        phase += (2.0f * M_PI * freq) / SAMPLE_RATE;
        if (phase >= 2.0f * M_PI) phase -= 2.0f * M_PI;
      }
    }
    size_t bw = 0;
    i2s_write(I2S_PORT, buf, chunk * 4, &bw, portMAX_DELAY);
  }
}

// Draw Birthday Cake with flickering candle
void drawCake(int x, int y, bool candleLit) {
  // Base plate
  display.drawFastHLine(x - 2, y + 16, 20, SSD1306_WHITE);
  // Bottom tier
  display.drawRoundRect(x, y + 8, 16, 8, 2, SSD1306_WHITE);
  // Top tier
  display.fillRect(x + 3, y + 3, 10, 5, SSD1306_WHITE);
  // Candle
  display.drawFastVLine(x + 7, y - 1, 4, SSD1306_WHITE);

  if (candleLit) {
    // Flickering Flame
    int flameH = random(2, 4);
    int flameOff = random(-1, 2);
    display.fillTriangle(x + 7 + flameOff, y - 2 - flameH,
                         x + 6, y - 1,
                         x + 8, y - 1, SSD1306_WHITE);
  } else {
    // Smoke rising from blown candle
    int smokeY = (millis() / 50) % 10;
    display.drawPixel(x + 7 + (smokeY % 3 - 1), y - 2 - smokeY, SSD1306_WHITE);
    display.drawPixel(x + 7 + (smokeY % 2), y - 5 - smokeY, SSD1306_WHITE);
  }
}

// Draw Party Hat
void drawPartyHat(int headX, int headY) {
  int apexX = headX + 12;
  int apexY = headY - 14;
  // Hat cone
  display.fillTriangle(apexX, apexY, headX + 4, headY + 2, headX + 20, headY + 2, SSD1306_WHITE);
  display.fillTriangle(apexX, apexY + 2, headX + 7, headY + 2, headX + 17, headY + 2, SSD1306_BLACK);
  // Pom-pom on top
  display.fillCircle(apexX, apexY - 1, 2, SSD1306_WHITE);
  // Polka dots on hat
  display.drawPixel(apexX - 2, apexY + 7, SSD1306_WHITE);
  display.drawPixel(apexX + 3, apexY + 10, SSD1306_WHITE);
}

// ---- Main Animated Singing Face ----
void drawCreativeSingingShow(int noteIndex, unsigned long t) {
  display.clearDisplay();

  // Head Bobbing & Beat Sway
  int bopX = (int)(sin((float)t / 200.0f) * 3.0f);
  int bopY = (int)(fabs(cos((float)t / 150.0f)) * 2.0f);

  int headCX = 64 + bopX;
  int eyeY   = 24 + bopY;

  // 1. Draw Confetti Particles
  updateConfetti();

  // 2. Party Hat on Head
  drawPartyHat(headCX - 12, eyeY - 12);

  // 3. Expressions (Switching eyes according to song progression)
  int expr = (noteIndex / 3) % 4;

  if (expr == 0) {
    // Happy Arc Eyes (^ ^)
    display.drawCircle(headCX - 22, eyeY + 2, 8, SSD1306_WHITE);
    display.fillRect(headCX - 31, eyeY + 2, 18, 9, SSD1306_BLACK); // Crop bottom half
    display.drawCircle(headCX + 22, eyeY + 2, 8, SSD1306_WHITE);
    display.fillRect(headCX + 13, eyeY + 2, 18, 9, SSD1306_BLACK);
  } else if (expr == 1) {
    // Winking Eye (Left Wink, Right Big Eye)
    // Left Wink
    display.drawLine(headCX - 30, eyeY + 2, headCX - 16, eyeY - 2, SSD1306_WHITE);
    display.drawLine(headCX - 30, eyeY - 2, headCX - 16, eyeY + 2, SSD1306_WHITE);
    // Right Eye
    display.fillRoundRect(headCX + 12, eyeY - 7, 20, 16, 8, SSD1306_WHITE);
    display.fillCircle(headCX + 22, eyeY, 3, SSD1306_BLACK);
  } else if (expr == 2) {
    // Big Excited Sparkle Eyes
    display.fillRoundRect(headCX - 32, eyeY - 7, 20, 16, 8, SSD1306_WHITE);
    display.fillCircle(headCX - 22, eyeY, 3, SSD1306_BLACK);
    display.fillCircle(headCX - 24, eyeY - 2, 2, SSD1306_WHITE);

    display.fillRoundRect(headCX + 12, eyeY - 7, 20, 16, 8, SSD1306_WHITE);
    display.fillCircle(headCX + 22, eyeY, 3, SSD1306_BLACK);
    display.fillCircle(headCX + 20, eyeY - 2, 2, SSD1306_WHITE);
  } else {
    // Cute Wide Oval Eyes
    display.fillRoundRect(headCX - 30, eyeY - 6, 18, 14, 7, SSD1306_WHITE);
    display.fillCircle(headCX - 21, eyeY, 2, SSD1306_BLACK);
    display.fillRoundRect(headCX + 12, eyeY - 6, 18, 14, 7, SSD1306_WHITE);
    display.fillCircle(headCX + 21, eyeY, 2, SSD1306_BLACK);
  }

  // 4. Singing Mouth (Dynamic Opening to pitch & tempo)
  float mouthAnim = (sin((float)t / 110.0f) + 1.0f) / 2.0f;
  int mouthW = 16 + (int)(mouthAnim * 12);
  int mouthH = 4  + (int)(mouthAnim * 12);
  int mouthY = eyeY + 22;

  display.fillRoundRect(headCX - mouthW / 2, mouthY - mouthH / 2, mouthW, mouthH, mouthH / 2, SSD1306_WHITE);
  if (mouthH > 6) {
    display.fillRoundRect(headCX - (mouthW - 4) / 2, mouthY - (mouthH - 4) / 2, mouthW - 4, mouthH - 4, (mouthH - 4) / 2, SSD1306_BLACK);
  }

  // 5. Floating Music Notes
  int noteX = 10 + (int)(sin((float)t / 180.0f) * 12.0f);
  int noteY = 28 - (int)((t / 25) % 30);
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(noteX, noteY);
  display.print((noteIndex % 2 == 0) ? "o" : "*");

  // 6. Mini Cake in bottom right corner
  drawCake(106, 42, true);

  // 7. Title Header
  display.setTextSize(1);
  display.setCursor(18, 0);
  display.print("HAPPY BIRTHDAY!");

  display.display();
}

// ---- Finale: Candle Blowout & Fireworks Banner ----
void playFinaleBlowout() {
  unsigned long start = millis();
  initConfetti();

  while (millis() - start < 6000) {
    unsigned long elapsed = millis() - start;
    display.clearDisplay();

    updateConfetti();

    // Kyoma blowing air face
    int headCX = 64;
    int eyeY   = 24;
    drawPartyHat(headCX - 12, eyeY - 12);

    if (elapsed < 1800) {
      // Blowing expression (puffed mouth)
      display.fillRoundRect(headCX - 30, eyeY - 6, 18, 14, 7, SSD1306_WHITE);
      display.fillCircle(headCX - 21, eyeY, 2, SSD1306_BLACK);
      display.fillRoundRect(headCX + 12, eyeY - 6, 18, 14, 7, SSD1306_WHITE);
      display.fillCircle(headCX + 21, eyeY, 2, SSD1306_BLACK);

      // Blowing mouth "O" shape
      display.drawCircle(headCX, eyeY + 22, 5, SSD1306_WHITE);

      // Air gusts moving towards cake
      int airX = headCX + 8 + (int)((elapsed / 10) % 35);
      display.drawFastHLine(airX, eyeY + 22, 6, SSD1306_WHITE);
      display.drawFastHLine(airX - 10, eyeY + 20, 4, SSD1306_WHITE);

      drawCake(106, 42, true);
    } else {
      // Candle is blown out! Big smile & fireworks banner
      display.drawCircle(headCX - 22, eyeY + 2, 8, SSD1306_WHITE);
      display.fillRect(headCX - 31, eyeY + 2, 18, 9, SSD1306_BLACK);
      display.drawCircle(headCX + 22, eyeY + 2, 8, SSD1306_WHITE);
      display.fillRect(headCX + 13, eyeY + 2, 18, 9, SSD1306_BLACK);

      // Huge Smile
      display.fillRoundRect(headCX - 16, eyeY + 16, 32, 14, 7, SSD1306_WHITE);
      display.fillRoundRect(headCX - 12, eyeY + 16, 24, 8,  4, SSD1306_BLACK);

      // Smoke rising from cake
      drawCake(106, 42, false);

      // Banner
      display.setTextSize(1);
      display.setCursor(16, 0);
      display.print("MAKE A WISH!");

      // Firework bursts
      if ((elapsed / 300) % 2 == 0) {
        display.drawCircle(20, 15, 6, SSD1306_WHITE);
        display.drawCircle(105, 12, 5, SSD1306_WHITE);
      }
    }

    display.display();
    delay(30);
  }
}

void setup() {
  Serial.begin(115200);
  Wire.begin(I2C_SDA, I2C_SCL);

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("SSD1306 init failed!");
  }
  display.clearDisplay();
  display.display();

  initSpeaker();
  initConfetti();

  Serial.println("Starting Creative Birthday Show!");
}

void loop() {
  // Play the song with creative animations
  for (int n = 0; n < NOTE_COUNT; n++) {
    int freq = happyBirthday[n].freq;
    int dur  = happyBirthday[n].dur;

    unsigned long start = millis();
    while (millis() - start < (unsigned long)dur) {
      drawCreativeSingingShow(n, millis());

      int sliceDur = min(40, (int)(dur - (millis() - start)));
      if (sliceDur > 0) playNote(freq, sliceDur);
    }
  }

  // Candle Blowout & Fireworks Finale
  playFinaleBlowout();
}
