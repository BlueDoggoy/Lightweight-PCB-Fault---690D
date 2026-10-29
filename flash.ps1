param([Parameter(Mandatory=$true)][string]$Port)
$ErrorActionPreference = 'Stop'
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\.platformio\packages\tool-esptoolpy\esptool.py" --chip esp32s3 --port $Port --baud 460800 write_flash 0x0 "$PSScriptRoot\artifacts\xiao_pcb_merged.bin"
if ($LASTEXITCODE -ne 0) { throw 'Flashing failed' }
