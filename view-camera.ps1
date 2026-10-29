param([string]$Port='COM6')
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\viewer.py" --port $Port
