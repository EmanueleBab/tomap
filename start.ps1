$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    throw 'Create the virtual environment and install requirements first (see README.md).'
}
& '.\.venv\Scripts\python.exe' app.py
