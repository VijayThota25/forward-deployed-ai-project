# Starts the Streamlit dashboard.
#
# This machine's Application Control policy blocks the pandas wheel that pip
# installs into a fresh venv (pandas._libs.tslib.pyd gets rejected), which
# breaks any st.dataframe/st.table call. There is a pre-existing, already-
# approved Python install at $env:LOCALAPPDATA\Python\bin\python.exe with a
# working pandas/streamlit/plotly stack, so the dashboard runs there instead
# of the project .venv. The backend has no pandas dependency, so it stays on
# .venv (see run_api.ps1). If this machine doesn't have that quirk, the venv
# python is used instead.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$systemPython = Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

$pythonExe = $venvPython
if (Test-Path $systemPython) {
    $check = & $systemPython -c "import pandas, streamlit, plotly" 2>&1
    if ($LASTEXITCODE -eq 0) {
        $pythonExe = $systemPython
    }
}

Write-Host "Using Python: $pythonExe"
$env:API_BASE_URL = "http://localhost:8000"
& $pythonExe -m streamlit run dashboard/app.py --server.port 8501
