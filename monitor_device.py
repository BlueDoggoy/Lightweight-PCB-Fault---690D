"""Capture a bounded serial log for device verification."""
import argparse
import time
from pathlib import Path
import serial

parser = argparse.ArgumentParser()
parser.add_argument('--port', default='COM6')
parser.add_argument('--seconds', type=int, default=15)
args = parser.parse_args()
lines = []
with serial.Serial(args.port, 115200, timeout=1) as device:
    end = time.monotonic() + args.seconds
    while time.monotonic() < end:
        line = device.readline().decode(errors='replace').strip()
        if line:
            print(line, flush=True)
            lines.append(line)
Path('artifacts/device_serial_latest.txt').write_text('\n'.join(lines), encoding='utf-8')
