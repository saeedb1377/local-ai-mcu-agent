/*
 * agent_bridge.ino - STM32duino-safe version for Nucleo F411RE
 */

#include <Arduino.h>

#define FW_VERSION        "1.0.0"
#define PROTO_VERSION     1
#define SERIAL_BAUD       115200
#define RX_BUF_LEN        64
#define LOG_DEPTH         16
#define SAMPLE_PERIOD_MS  500

#define USE_SIM_TEMP      1

#ifdef LED_BUILTIN
  #define LED_PIN         LED_BUILTIN
#else
  #define LED_PIN         PA5
#endif

#define THRESH_MIN        -40.0f
#define THRESH_MAX        125.0f

static char     rxBuf[RX_BUF_LEN];
static uint8_t  rxLen      = 0;
static bool     rxOverflow = false;

static bool     ledState   = false;
static bool     autoMode   = true;
static float    threshold  = 35.0f;
static bool     alarm      = false;

static float    logBuf[LOG_DEPTH];
static uint8_t  logCount   = 0;
static uint8_t  logHead    = 0;
static float    lastTemp   = 0.0f;
static uint32_t lastSample = 0;

// Simple periodic temperature simulation (no sin() to avoid math lib issues)
static float readTemp() {
#if USE_SIM_TEMP
  uint32_t ms = millis();
  float t = ms / 1000.0f;
  // Triangle wave + small noise, crosses 35.0 threshold periodically
  float wave = 32.0f + 6.0f * (2.0f * abs((int)((t + 120.0f) / 120.0f) % 2 - 1) - 1.0f);
  int noise = random(-25, 26);
  return wave + (noise / 100.0f);
#else
  int raw = analogRead(A0);
  return raw * (100.0f / 1023.0f);
#endif
}

static void pushLog(float v) {
  logBuf[logHead] = v;
  logHead = (logHead + 1) % LOG_DEPTH;
  if (logCount < LOG_DEPTH) logCount++;
}

static void applyOutputs() {
  bool want = autoMode ? alarm : ledState;
  ledState = want;
  digitalWrite(LED_PIN, want ? HIGH : LOW);
}

static void sendErr(uint8_t code, const char *detail) {
  Serial.print("ERR ");
  Serial.print(code);
  Serial.print(' ');
  Serial.println(detail);
}

static void sendStatus() {
  Serial.print("OK LED=");    Serial.print(ledState ? "ON" : "OFF");
  Serial.print(" MODE=");     Serial.print(autoMode ? "AUTO" : "MANUAL");
  Serial.print(" TEMP=");     Serial.print(lastTemp, 2);
  Serial.print(" THRESH=");   Serial.print(threshold, 2);
  Serial.print(" ALARM=");    Serial.print(alarm ? 1 : 0);
  Serial.print(" UPTIME=");   Serial.println(millis() / 1000UL);
}

static void sendLog() {
  Serial.print("OK LOG=");
  if (logCount == 0) { Serial.println(); return; }
  uint8_t start = (logHead + LOG_DEPTH - logCount) % LOG_DEPTH;
  for (uint8_t i = 0; i < logCount; i++) {
    if (i) Serial.print(',');
    Serial.print(logBuf[(start + i) % LOG_DEPTH], 2);
  }
  Serial.println();
}

static void handleLine(char *line) {
  char *verb = line;
  char *arg  = NULL;
  for (char *p = line; *p; p++) {
    if (*p == ' ' || *p == '\t') { *p = '\0'; arg = p + 1; break; }
  }
  for (char *p = verb; *p; p++) *p = toupper(*p);
  if (arg) { while (*arg == ' ') arg++; for (char *p = arg; *p; p++) *p = toupper(*p); }
  if (verb[0] == '\0') return;

  if (!strcmp(verb, "PING")) {
    Serial.println("OK PONG");

  } else if (!strcmp(verb, "ID?")) {
    Serial.print("OK FW="); Serial.print(FW_VERSION);
    Serial.print(" PROTO="); Serial.println(PROTO_VERSION);

  } else if (!strcmp(verb, "HELP")) {
    Serial.println("OK VERBS=PING,ID?,HELP,STATUS?,TEMP?,LOG?,LED,MODE,MODE?,THRESH,THRESH?,ALARM");

  } else if (!strcmp(verb, "STATUS?")) {
    sendStatus();

  } else if (!strcmp(verb, "TEMP?")) {
    Serial.print("OK TEMP="); Serial.println(lastTemp, 2);

  } else if (!strcmp(verb, "LOG?")) {
    sendLog();

  } else if (!strcmp(verb, "LED")) {
    if (autoMode)            { sendErr(5, "AUTO_MODE_ACTIVE"); return; }
    if (!arg)                { sendErr(2, "EXPECTED_ON_OR_OFF"); return; }
    if      (!strcmp(arg, "ON"))  ledState = true;
    else if (!strcmp(arg, "OFF")) ledState = false;
    else                     { sendErr(2, "EXPECTED_ON_OR_OFF"); return; }
    applyOutputs();
    Serial.print("OK LED="); Serial.println(ledState ? "ON" : "OFF");

  } else if (!strcmp(verb, "MODE?")) {
    Serial.print("OK MODE="); Serial.println(autoMode ? "AUTO" : "MANUAL");

  } else if (!strcmp(verb, "MODE")) {
    if (!arg)                       { sendErr(2, "EXPECTED_AUTO_OR_MANUAL"); return; }
    if      (!strcmp(arg, "AUTO"))   autoMode = true;
    else if (!strcmp(arg, "MANUAL")) autoMode = false;
    else                            { sendErr(2, "EXPECTED_AUTO_OR_MANUAL"); return; }
    applyOutputs();
    Serial.print("OK MODE="); Serial.println(autoMode ? "AUTO" : "MANUAL");

  } else if (!strcmp(verb, "THRESH?")) {
    Serial.print("OK THRESH="); Serial.println(threshold, 2);

  } else if (!strcmp(verb, "THRESH")) {
    if (!arg) { sendErr(2, "EXPECTED_NUMBER"); return; }
    char *end;
    float v = strtod(arg, &end);
    if (end == arg)                        { sendErr(2, "EXPECTED_NUMBER"); return; }
    if (v < THRESH_MIN || v > THRESH_MAX)  { sendErr(3, "THRESH_-40_TO_125"); return; }
    threshold = v;
    Serial.print("OK THRESH="); Serial.println(threshold, 2);

  } else if (!strcmp(verb, "ALARM")) {
    if (!arg || strcmp(arg, "CLR")) { sendErr(2, "EXPECTED_CLR"); return; }
    alarm = false;
    applyOutputs();
    Serial.println("OK ALARM=0");

  } else {
    sendErr(1, "NOT_IN_WHITELIST");
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(500);  // STM32-safe: wait for Serial instead of while(!Serial) which can hang
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  randomSeed(millis());  // STM32-safe: no analogRead() which can hang before ADC init
  lastTemp = readTemp();
  lastSample = millis();
}

void loop() {
  uint32_t now = millis();
  if (now - lastSample >= SAMPLE_PERIOD_MS) {
    lastSample = now;
    lastTemp = readTemp();
    pushLog(lastTemp);
    if (lastTemp > threshold) alarm = true;
    applyOutputs();
  }

  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (rxOverflow) { sendErr(4, "LINE_TOO_LONG"); }
      else            { rxBuf[rxLen] = '\0'; handleLine(rxBuf); }
      rxLen = 0;
      rxOverflow = false;
      continue;
    }
    if (rxLen < RX_BUF_LEN - 1) rxBuf[rxLen++] = c;
    else                        rxOverflow = true;
  }
}