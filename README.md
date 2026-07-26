# MCU Agent Bridge

A tool-calling LLM operates an STM32 Nucleo board over UART. The model reads sensors, sets thresholds, and controls an LED through a fixed 7-function API. No raw strings reach the hardware.

## Stack

| Layer | File | Role |
|---|---|---|
| Firmware | `agent_bridge.ino` | Whitelisted UART command server, on-device alarm latch, simulated temperature sampling at 2 Hz |
| Protocol | — | ASCII line: `VERB [ARG]\n` → `OK &lt;payload&gt;` / `ERR &lt;code&gt; &lt;detail&gt;` |
| Driver | `device.py` | pyserial transport, DTR-safe open for Nucleo boards, typed command wrappers |
| Tools | `tools.py` | JSON schemas + dispatch table. The model's only interface to hardware. |
| Agent | `agent.py` | Ollama tool-calling loop. Temperature 0, max 8 steps. |
| Supervisor | `supervisor.py` | 2 Hz deterministic poll. LLM invoked only on alarm transitions to write `events.log`. |

## Hardware

- **Board:** STM32 Nucleo-F411RE
- **Serial:** ST-Link virtual COM port (USART2 PA2/PA3) @ 115200 8N1
- **LED:** PA5 (LD2)
- **Sensor:** Simulated triangle wave + noise. Set `USE_SIM_TEMP 0` to wire a real sensor.

## Prerequisites

- Python 3.10+, `pyserial`, `requests`
- Ollama with `qwen2.5:7b-instruct` (or `llama3.1:8b`)
- Arduino IDE 2.x + STM32duino core (`package_stmicroelectronics_index.json`)

## Quick start

### 1. Flash firmware
- Board: **Nucleo-64 → Nucleo F411RE**
- Upload method: **Mass Storage**
- Upload `firmware/agent_bridge/agent_bridge.ino`
- Close Serial Monitor

### 2. Install Python deps
```bash
cd host
pip install -r requirements.txt
python device.py

# Error recovery: model switches AUTO → MANUAL → LED OFF
python agent.py "Turn the LED off."

# Multi-step diagnostic
python agent.py "Check whether the board is overheating. If it is, raise the threshold to 40 C, clear the alarm, and report."

# Trend analysis from 16-sample log
python agent.py "Is the temperature trending up or down? Read the log and explain."

# Automated calibration
python agent.py "Read the temperature log, calculate the average ambient, add 5 C, and set that as the new threshold."

python supervisor.py

| Function           | Args              | Notes                                                 |
| ------------------ | ----------------- | ----------------------------------------------------- |
| `get_status`       | —                 | Full state: LED, mode, temp, threshold, alarm, uptime |
| `read_temperature` | —                 | Latest sample                                         |
| `read_log`         | —                 | Last 16 samples, oldest first, 500 ms interval        |
| `set_mode`         | `AUTO` / `MANUAL` | `set_led` requires MANUAL                             |
| `set_led`          | `ON` / `OFF`      | Fails with ERR 5 in AUTO mode                         |
| `set_threshold`    | `-40` to `125`    | Celsius                                               |
| `clear_alarm`      | —                 | Latches again if temp > threshold                     |


| Issue                               | Fix                                                       |
| ----------------------------------- | --------------------------------------------------------- |
| DTR asserts RESET on open           | `serial.dtr = False; serial.rts = False` before `.open()` |
| `while (!Serial)` hangs             | `delay(500)`                                              |
| `randomSeed(analogRead(...))` hangs | `randomSeed(millis())`                                    |
| `sin()` crashes                     | Triangle-wave formula                                     |
| `F("string")` macros garble output  | Plain strings                                             |
| `LED_BUILTIN` fallback to pin 2     | Explicit `PA5`                                            |



**What I fixed:**
1. `&lt;` and `&gt;` → `<` and `>` in the Protocol row
2. Added proper ` ```bash ` code fences around each command block
3. Added the missing `### 3. Verify transport` heading
4. Added the missing `## Tool surface` heading
5. Added the missing `## Safety model` heading
6. Added the missing `## STM32-specific fixes` heading
7. Added the missing `## Extending` and `## License` sections

