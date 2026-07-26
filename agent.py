"""
agent.py - the tool-calling loop, running entirely on a local open model.

    python agent.py "the board is running hot, investigate and fix it"

No cloud, no API key. Ollama serves the model on 127.0.0.1:11434.
"""

from __future__ import annotations

import json
import sys

import requests

from device import Device
from tools import TOOL_SCHEMAS, build_dispatch, call_tool

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:7b-instruct"   # any tool-calling open model works here
MAX_STEPS = 8
HTTP_TIMEOUT_S = 180

SYSTEM_PROMPT = """You operate a microcontroller over a fixed set of tools.

Rules:
- Never guess the device state. Call get_status or read_temperature to find out.
- set_led requires MANUAL mode. If a call fails, read the error, fix the
  precondition, and retry once. Do not retry the same failing call unchanged.
- The device latches its own alarm when temperature exceeds the threshold.
  Clearing the alarm does not lower the temperature.
- When you are done, reply in plain text: what you observed, what you changed,
  and the resulting state. Two or three sentences. No tool calls in that reply.
"""


def chat(messages: list[dict]) -> dict:
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": messages,
            "tools": TOOL_SCHEMAS,
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=HTTP_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()["message"]


def run(task: str, dev: Device, verbose: bool = True) -> str:
    dispatch = build_dispatch(dev)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]

    for step in range(MAX_STEPS):
        msg = chat(messages)
        messages.append(msg)
        calls = msg.get("tool_calls") or []

        if not calls:
            return msg.get("content", "").strip()

        for call in calls:
            fn = call["function"]
            name = fn["name"]
            args = fn.get("arguments") or {}
            if isinstance(args, str):          # some backends send a JSON string
                args = json.loads(args or "{}")

            result = call_tool(dispatch, name, args)
            if verbose:
                print(f"  [{step}] {name}({args}) -> {result}")

            messages.append(
                {"role": "tool", "name": name, "content": json.dumps(result)}
            )

    return "step limit reached without a final answer"


def main() -> None:
    task = " ".join(sys.argv[1:]) or (
        "Check whether the board is overheating. If it is, raise the threshold "
        "to 40 C, clear the alarm, and report the new state."
    )
    with Device() as dev:
        print(f"device on {dev.port}, model {MODEL}\ntask: {task}\n")
        print("\n" + run(task, dev))


if __name__ == "__main__":
    main()
