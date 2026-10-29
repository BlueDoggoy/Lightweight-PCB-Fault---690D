$ErrorActionPreference = 'Stop'
if (Test-Path P:\) { throw 'P: is occupied. Use another unused drive letter in this script.' }
subst P: $PSScriptRoot
try {
    $env:PLATFORMIO_CORE_DIR = 'P:\.platformio'
    & P:\.venv\Scripts\python.exe -m platformio run -d P:\firmware -j 2
    if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed' }
    & P:\.venv\Scripts\python.exe P:\.platformio\packages\tool-esptoolpy\esptool.py --chip esp32s3 merge_bin -o P:\artifacts\xiao_pcb_merged.bin 0x0 P:\firmware\.pio\build\xiao\bootloader.bin 0x8000 P:\firmware\.pio\build\xiao\partitions.bin 0xe000 P:\.platformio\packages\framework-arduinoespressif32\tools\partitions\boot_app0.bin 0x10000 P:\firmware\.pio\build\xiao\firmware.bin
    if ($LASTEXITCODE -ne 0) { throw 'Firmware merge failed' }
} finally { subst P: /D }
