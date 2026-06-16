@echo off
title PMESP - Sistema de Controle de Viaturas
color 0C

echo.
echo  ==========================================
echo    PMESP - Sistema de Controle de Viaturas
echo  ==========================================
echo.

cd /d "%~dp0"

:: Abre o navegador apos 2 segundos
timeout /t 2 /nobreak >nul
start http://localhost:5000

echo  Servidor iniciando em: http://localhost:5000
echo  Pressione CTRL+C para encerrar
echo.
echo  Usuarios:
echo    Admin:  admin / admin
echo    Teste:  teste / teste
echo  ==========================================
echo.

.venv\Scripts\python.exe app.py

pause
