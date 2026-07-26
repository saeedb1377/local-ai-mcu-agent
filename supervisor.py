"""
supervisor.py - the version that is not a toy.

The agent is kept out of the control path. A deterministic loop polls at
2 Hz; the firmware already enforces the safety rule. The model is invoked
only on a state *transition*, and only to produce a written explanation.

That separation is the whole point: a 7B model at 3 tokens/s cannot be a
control loop, but it is a perfectly good operator and report writer.
"""

from __future__ import annotations

import datetime as dt
import time

from agent import run
from device import Device, DeviceError

POLL_S = 0.5
REPORT_PATH = "events.log"


def log(line: str) -> None:
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    entry = f"{stamp}  {line}"
    print(entry)
    with open(REPORT_PATH, "a", encoding="utf-8") as fh:
        fh.write(entry + "\n")


def main() -> None:
    with Device() as dev:
        log(f"supervisor start on {dev.port}, firmware {dev.identify()}")
        previous: bool | None = None

        while True:
            try:
                state = dev.status()
            except DeviceError as exc:
                log(f"device error: {exc}")
                time.sleep(1.0)
                continue

            alarm = bool(state["alarm"])
            if previous is not None and alarm != previous:
                log(f"transition alarm {previous} -> {alarm}, state={state}")
                samples = dev.read_log()
                task = (
                    f"An alarm transition to {alarm} just occurred. "
                    f"Device state: {state}. Recent samples (oldest first): {samples}. "
                    "Explain the likely cause from the trend and state whether the "
                    "threshold is set appropriately. Do not change anything."
                )
                log("agent: " + run(task, dev, verbose=False).replace("\n", " "))

            previous = alarm
            time.sleep(POLL_S)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped")
