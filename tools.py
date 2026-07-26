"""
tools.py - the only surface the model is allowed to touch.

The model never emits a serial command. It picks a name from this fixed
list and supplies typed arguments, which are validated three times:
in the JSON schema, in device.py, and again in the firmware.
"""

from __future__ import annotations

from typing import Any, Callable

from device import Device, DeviceError

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_status",
            "description": "Read the full device state: LED, mode, temperature, threshold, alarm, uptime.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_temperature",
            "description": "Read the most recent temperature sample in degrees Celsius.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_log",
            "description": "Read the last 16 temperature samples, oldest first, one every 500 ms.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_mode",
            "description": (
                "Set the control mode. AUTO means the device drives the LED from its own "
                "threshold rule. MANUAL means the LED is under host control. set_led only "
                "works in MANUAL."
            ),
            "parameters": {
                "type": "object",
                "properties": {"mode": {"type": "string", "enum": ["AUTO", "MANUAL"]}},
                "required": ["mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_led",
            "description": "Turn the indicator LED on or off. Requires MANUAL mode.",
            "parameters": {
                "type": "object",
                "properties": {"state": {"type": "string", "enum": ["ON", "OFF"]}},
                "required": ["state"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_threshold",
            "description": "Set the alarm threshold in degrees Celsius. Allowed range -40 to 125.",
            "parameters": {
                "type": "object",
                "properties": {
                    "celsius": {"type": "number", "minimum": -40, "maximum": 125}
                },
                "required": ["celsius"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_alarm",
            "description": "Clear the latched alarm flag. It re-latches if temperature exceeds the threshold again.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def build_dispatch(dev: Device) -> dict[str, Callable[..., Any]]:
    return {
        "get_status": lambda: dev.status(),
        "read_temperature": lambda: {"temperature_c": dev.read_temperature()},
        "read_log": lambda: {"samples_c": dev.read_log()},
        "set_mode": lambda mode: {"mode": dev.set_mode(mode)},
        "set_led": lambda state: {"led": dev.set_led(state)},
        "set_threshold": lambda celsius: {"threshold_c": dev.set_threshold(celsius)},
        "clear_alarm": lambda: {"alarm": dev.clear_alarm()},
    }


def call_tool(dispatch: dict[str, Callable[..., Any]], name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Never raises. Failures come back as data so the model can recover."""
    fn = dispatch.get(name)
    if fn is None:
        return {"error": f"unknown tool {name!r}", "available": sorted(dispatch)}
    try:
        return {"ok": True, "result": fn(**args)}
    except DeviceError as exc:
        return {"ok": False, "error": str(exc)}
    except TypeError as exc:
        return {"ok": False, "error": f"bad arguments for {name}: {exc}"}
