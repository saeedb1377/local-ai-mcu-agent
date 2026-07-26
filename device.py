"""
device.py - transport layer between the host and the MCU.

Nothing in this file knows that an LLM exists. It is a plain, testable
driver: one request line out, one response line back, under a lock.
"""

from __future__ import annotations

import threading
import time

import serial
from serial.tools import list_ports

BAUD = 115200
READ_TIMEOUT_S = 1.5
BOOT_DELAY_S = 2.0  # boards that auto-reset when DTR is asserted


class DeviceError(RuntimeError):
    """Device replied ERR, timed out, or sent a malformed frame."""


def autodetect_port() -> str:
    """Return the first plausible USB serial port, or raise."""
    ports = list_ports.comports()
    # Prefer ST-Link / STM32 / Arduino / CP210x / CH340 over Bluetooth
    preferred = [
        p.device for p in ports
        if any(k in (p.description or "").upper() for k in ("STLINK", "STM32", "ARDUINO", "CP210", "CH340", "USB SERIAL"))
    ]
    if preferred:
        return preferred[0]
    # Fallback: any COM/tty port
    candidates = [
        p.device for p in ports
        if any(k in (p.device or "") for k in ("ttyACM", "ttyUSB", "usbmodem", "usbserial", "COM"))
    ]
    if not candidates:
        raise DeviceError("no USB serial port found - check the cable and drivers")
    return candidates[0]

def parse_kv(payload: str) -> dict[str, str]:
    """'LED=ON MODE=AUTO TEMP=31.20' -> {'LED': 'ON', ...}"""
    out: dict[str, str] = {}
    for token in payload.split():
        if "=" in token:
            k, v = token.split("=", 1)
            out[k] = v
    return out


class Device:
    def __init__(self, port: str | None = None, baud: int = BAUD) -> None:
        self.port = port or autodetect_port()
        self._ser = serial.Serial()
        self._ser.port = self.port
        self._ser.baudrate = baud
        self._ser.timeout = READ_TIMEOUT_S
        self._ser.dtr = False
        self._ser.rts = False
        self._ser.open()
        self._lock = threading.Lock()
        time.sleep(BOOT_DELAY_S)
        self._ser.reset_input_buffer()
        self._handshake()

    # -- lifecycle -------------------------------------------------------

    def close(self) -> None:
        try:
            self._ser.close()
        except Exception:
            pass

    def __enter__(self) -> "Device":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _handshake(self, attempts: int = 5) -> None:
        for _ in range(attempts):
            try:
                if self._txn("PING") == "PONG":
                    return
            except DeviceError:
                time.sleep(0.4)
        raise DeviceError(f"no PONG from {self.port} - wrong port, wrong baud, or serial monitor open")

    # -- core transaction ------------------------------------------------

    def _txn(self, line: str) -> str:
        with self._lock:
            self._ser.reset_input_buffer()
            self._ser.write((line + "\n").encode("ascii"))
            self._ser.flush()
            raw = self._ser.readline().decode("ascii", errors="replace").strip()
        if not raw:
            raise DeviceError(f"timeout waiting for reply to {line!r}")
        if raw.startswith("ERR"):
            raise DeviceError(raw)
        if not raw.startswith("OK"):
            raise DeviceError(f"malformed frame: {raw!r}")
        return raw[2:].strip()

    # -- typed commands (host-side validation mirrors the firmware) -------

    def identify(self) -> dict[str, str]:
        return parse_kv(self._txn("ID?"))

    def status(self) -> dict[str, object]:
        kv = parse_kv(self._txn("STATUS?"))
        return {
            "led": kv.get("LED"),
            "mode": kv.get("MODE"),
            "temperature_c": float(kv["TEMP"]),
            "threshold_c": float(kv["THRESH"]),
            "alarm": kv.get("ALARM") == "1",
            "uptime_s": int(kv["UPTIME"]),
        }

    def read_temperature(self) -> float:
        return float(parse_kv(self._txn("TEMP?"))["TEMP"])

    def read_log(self) -> list[float]:
        payload = parse_kv(self._txn("LOG?")).get("LOG", "")
        return [float(x) for x in payload.split(",") if x]

    def set_led(self, state: str) -> str:
        state = state.upper()
        if state not in ("ON", "OFF"):
            raise DeviceError("led state must be ON or OFF")
        return parse_kv(self._txn(f"LED {state}"))["LED"]

    def set_mode(self, mode: str) -> str:
        mode = mode.upper()
        if mode not in ("AUTO", "MANUAL"):
            raise DeviceError("mode must be AUTO or MANUAL")
        return parse_kv(self._txn(f"MODE {mode}"))["MODE"]

    def set_threshold(self, celsius: float) -> float:
        celsius = float(celsius)
        if not -40.0 <= celsius <= 125.0:
            raise DeviceError("threshold must be between -40 and 125 C")
        return float(parse_kv(self._txn(f"THRESH {celsius:.2f}"))["THRESH"])

    def clear_alarm(self) -> bool:
        self._txn("ALARM CLR")
        return False


if __name__ == "__main__":
    with Device() as dev:
        print("port     :", dev.port)
        print("identity :", dev.identify())
        print("status   :", dev.status())
        print("log      :", dev.read_log())
