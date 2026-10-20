// ============================================================
// KYOMA - Simple Mic Dead/Alive Test
// Shows raw I2S values + clear DEAD/ALIVE status on OLED
// ============================================================

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <driver/i2s.h>

#define I2C_SDA   6
#define I2C_SCL   7
#define MIC_SCK  20
#define MIC_WS   10
#define MIC_SD    2

#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT  64
#define OLED_RESET     -1
#define I2S_PORT    I2S_NUM_0
#define SAMPLE_RATE 16000

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

void initMic() {
  i2s_config_t cfg = {
    .mode                = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate         = SAMPLE_RATE,
    .bits_per_sample     = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format      = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format= I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags    = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count       = 4,
    .dma_buf_len         = 256,
    .use_apll            = false,
    .tx_desc_auto_clear  = false,
    .fixed_mclk          = 0
  };
  i2s_pin_config_t pins = {
    .bck_io_num   = MIC_SCK,
    .ws_io_num    = MIC_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num  = MIC_SD
  };
  i2s_driver_install(I2S_PORT, &cfg, 0, NULL);
  i2s_set_pin(I2S_PORT, &pins);
}

void setup() {
  Serial.begin(115200);
  Wire.begin(I2C_SDA, I2C_SCL);
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(20, 28);
  display.setTextSize(1);
  display.print("Initializing mic...");
  display.display();
  delay(500);
  initMic();
}

void loop() {
  int32_t raw[64];
  size_t bytesRead = 0;
  i2s_read(I2S_PORT, raw, sizeof(raw), &bytesRead, 30);
  int samples = bytesRead / sizeof(int32_t);

  // Find max absolute value and check if ALL samples are zero
  int32_t maxVal = 0;
  int zeroCount = 0;
  for (int i = 0; i < samples; i++) {
    int32_t v = abs(raw[i]);
    if (v > maxVal) maxVal = v;
    if (raw[i] == 0) zeroCount++;
  }

  // Convert to 16-bit range for display
  int16_t amplitude = (int16_t)(maxVal >> 14);
  bool allZero = (zeroCount == samples);
  bool micAlive = (amplitude > 10); // any non-trivial signal

  // Serial output
  Serial.printf("Samples=%d  MaxRaw=%ld  Amp16=%d  ZeroCount=%d  %s\n",
    samples, maxVal, amplitude, zeroCount,
    allZero ? "ALL ZERO - MIC DEAD/DISCONNECTED" : (micAlive ? "SIGNAL DETECTED" : "near silence"));

  // ---- Draw OLED ----
  display.clearDisplay();

  // Status banner - BIG text
  if (allZero) {
    // ALL ZERO: definitely dead or disconnected
    display.fillRect(0, 0, 128, 32, SSD1306_WHITE);
    display.setTextColor(SSD1306_BLACK);
    display.setTextSize(2);
    display.setCursor(18, 8);
    display.print("X DEAD");
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(4, 38);
    display.print("All samples = 0");
    display.setCursor(4, 50);
    display.print("Check wiring on D0");
  } else if (micAlive) {
    // Signal detected - ALIVE
    display.fillRect(0, 0, 128, 32, SSD1306_WHITE);
    display.setTextColor(SSD1306_BLACK);
    display.setTextSize(2);
    display.setCursor(8, 8);
    display.print("OK ALIVE");
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(4, 38);
    display.print("Amp: ");
    display.print(amplitude);
    display.setCursor(4, 50);
    display.print("Mic is working!");
  } else {
    // Near zero but not all zero - silent but connected
    display.setTextSize(2);
    display.setCursor(4, 4);
    display.print("SILENCE");
    display.setTextSize(1);
    display.setCursor(4, 38);
    display.print("Amp: ");
    display.print(amplitude);
    display.setCursor(4, 50);
    display.print("Clap to confirm alive");
  }

  // Raw value readout bottom
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  char buf[32];
  snprintf(buf, sizeof(buf), "raw=%ld", maxVal);
  display.setCursor(70, 50);
  display.print(buf);

  display.display();
  delay(80);
}
