@echo off
title Gestor Financiero - Iniciando...
echo Iniciando Gestor Financiero Correduria...
echo.

:: Rutas relativas a la carpeta de este .bat (funciona aunque se mueva el proyecto)
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

:: Node portable (no esta en el PATH del sistema)
set "NODE_DIR=%LOCALAPPDATA%\Programs\nodejs-portable\node-v22.14.0-win-x64"
if not exist "%NODE_DIR%\npx.cmd" (
    echo ERROR: no se encuentra Node en "%NODE_DIR%".
    pause
    exit /b 1
)
set "PATH=%NODE_DIR%;%PATH%"

if not exist "%BACKEND%\venv\Scripts\python.exe" (
    echo ERROR: no se encuentra el entorno virtual en "%BACKEND%\venv".
    pause
    exit /b 1
)

:: PostgreSQL 18 (puerto 5433, el que usa backend\.env)
sc query postgresql-x64-18 | find "RUNNING" >nul 2>&1
if errorlevel 1 (
    echo Arrancando PostgreSQL...
    net start postgresql-x64-18 >nul 2>&1
    timeout /t 3 /nobreak >nul
)

:: Cerrar procesos anteriores en 8000 y 5173
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8000 " ^| find "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find ":5173 " ^| find "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
timeout /t 2 /nobreak >nul

:: Arrancar backend
echo Arrancando backend...
start "Backend" /D "%BACKEND%" cmd /k "venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
timeout /t 4 /nobreak >nul

:: Compilar frontend (garantiza codigo fresco, sin cache)
echo Compilando frontend...
pushd "%FRONTEND%"
call npx vite build
if errorlevel 1 (
    echo ERROR: fallo la compilacion del frontend.
    popd
    pause
    exit /b 1
)
popd

:: Arrancar frontend desde el build compilado
echo Arrancando frontend...
start "Frontend" /D "%FRONTEND%" cmd /k "npx vite preview --port 5173"
timeout /t 4 /nobreak >nul

:: Abrir navegador
start http://localhost:5173

echo Listo. Puedes cerrar esta ventana.
timeout /t 3 /nobreak >nul
exit
