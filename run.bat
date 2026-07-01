@echo off
REM KoeRelay ランチャー(Windows)。ダブルクリックで起動。
REM 初回は依存の取得で少し時間がかかります。uv が必要:
REM   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo uv が見つかりません。先に uv をインストールしてください:
  echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
  pause
  exit /b 1
)

echo 依存を同期しています(初回は時間がかかります)...
uv sync --extra full
if errorlevel 1 (
  echo 依存の同期に失敗しました。
  pause
  exit /b 1
)

echo KoeRelay を起動します...
uv run python -m koerelay.main
