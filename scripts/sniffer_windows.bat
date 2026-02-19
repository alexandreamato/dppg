@echo off
REM Serial Sniffer para Vasoquant 1000 - Windows
REM =============================================

echo.
echo  ====================================================
echo   SERIAL SNIFFER - Vasoquant 1000
echo  ====================================================
echo.

REM Verificar se Python está instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERRO: Python nao encontrado!
    echo  Instale Python 3: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM Verificar se pyserial está instalado
python -c "import serial" >nul 2>&1
if %errorlevel% neq 0 (
    echo  Instalando pyserial...
    pip install pyserial
    echo.
)

echo  Modos de operacao:
echo.
echo  1. Listar portas disponiveis
echo  2. Modo PASSIVO - Escutar COM2 (Vasoquant direto)
echo  3. Modo PROXY - Interceptar comunicacao
echo  4. Sair
echo.

set /p choice="  Escolha [1-4]: "

if "%choice%"=="1" (
    python serial_sniffer.py --list
    pause
    goto :eof
)

if "%choice%"=="2" (
    echo.
    set /p port="  Porta do Vasoquant [COM2]: "
    if "%port%"=="" set port=COM2
    echo.
    echo  Iniciando modo passivo em %port%...
    echo  Pressione Ctrl+C para parar.
    echo.
    python serial_sniffer.py --listen %port%
    pause
    goto :eof
)

if "%choice%"=="3" (
    echo.
    echo  MODO PROXY - Configuracao:
    echo.
    echo  Voce precisa do com0com instalado!
    echo  Download: https://sourceforge.net/projects/com0com/
    echo.
    echo  Configuracao tipica:
    echo    - Vasoquant conectado em COM2
    echo    - com0com cria par COM10 ^<-^> COM11
    echo    - Vasoview configurado para COM10
    echo    - Sniffer conecta COM2 e COM11
    echo.
    set /p device_port="  Porta do Vasoquant [COM2]: "
    if "%device_port%"=="" set device_port=COM2
    set /p app_port="  Porta virtual (par do Vasoview) [COM11]: "
    if "%app_port%"=="" set app_port=COM11
    echo.
    echo  Iniciando proxy: %device_port% ^<-^> %app_port%
    echo  Agora inicie o Vasoview e exporte exames.
    echo  Pressione Ctrl+C para parar.
    echo.
    python serial_sniffer.py --proxy %device_port% %app_port%
    pause
    goto :eof
)

if "%choice%"=="4" (
    exit /b 0
)

echo  Opcao invalida!
pause
