# Windows startup dependency-check known issue

The Windows source-checkout startup script can incorrectly report that packages are missing after pip has already confirmed that all packages are installed. This is caused by PowerShell function return behavior mixing process output with boolean return values.

Temporary workaround:

```powershell
cd D:\OneDrive\local-apps\IZ_clinical-notes-analyzer
$env:IZ_CNA_ENV_FILE = "$env:LOCALAPPDATA\IZ Clinical Notes Analyzer\.env"
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m uvicorn app.desktop_main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Then open:

```text
http://localhost:8000
```
