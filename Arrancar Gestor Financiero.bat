@echo off
title Gestor Financiero - Iniciando...
echo Iniciando Gestor Financiero Correduria...
echo.

:: PostgreSQL
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
start "Backend" cmd /k "cd /d C:\Users\Cris\desktop\ModelofinancieroDAVID\backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
timeout /t 4 /nobreak >nul

:: Compilar frontend (garantiza codigo fresco, sin cache)
echo Compilando frontend...
cd /d C:\Users\Cris\desktop\ModelofinancieroDAVID\frontend
call npx vite build

:: Arrancar frontend desde el build compilado
echo Arrancando frontend...
start "Frontend" cmd /k "cd /d C:\Users\Cris\desktop\ModelofinancieroDAVID\frontend && npx vite preview --port 5173"
timeout /t 4 /nobreak >nul

:: Abrir navegador
start http://localhost:5173

echo Listo. Puedes cerrar esta ventana.
timeout /t 3 /nobreak >nul
exit
