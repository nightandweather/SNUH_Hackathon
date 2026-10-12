@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
where docker >nul 2>nul
if errorlevel 1 (
  echo Docker Desktop을 설치하고 실행한 뒤 다시 시작하세요.
  pause
  exit /b 1
)
docker info >nul 2>nul
if errorlevel 1 (
  echo Docker Desktop이 실행되어 있지 않습니다. 실행한 뒤 다시 시작하세요.
  pause
  exit /b 1
)
docker compose up --build -d
if errorlevel 1 (
  echo 실행에 실패했습니다. 위 오류와 README.md를 확인하세요.
  pause
  exit /b 1
)
echo PeriCare 시작 완료. 기본 접속 주소: http://localhost:8000
echo .env에서 APP_PORT를 변경했다면 해당 포트로 접속하세요.
start http://localhost:8000
pause
