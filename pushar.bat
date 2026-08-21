@echo off
REM Publica os commits locais no GitHub.
REM
REM   pushar.bat                 -> este repo, pedindo confirmacao
REM   pushar.bat <pasta>         -> outro repo, pedindo confirmacao
REM   pushar.bat /S              -> sem perguntar (use no terminal do VS Code,
REM   pushar.bat <pasta> /S         onde o prompt do CHOICE nao funciona)
setlocal
set AUTO=
set DESTINO=
for %%a in (%*) do (
    if /i "%%~a"=="/S" (set AUTO=1) else (set DESTINO=%%~a)
)
if defined DESTINO (cd /d "%DESTINO%") else (cd /d "%~dp0")

for /f "delims=" %%b in ('git branch --show-current') do set BRANCH=%%b
if "%BRANCH%"=="" (
    echo ERRO: nao estou em uma branch ^(HEAD solto^). Nada foi enviado.
    goto fim
)
for /f "delims=" %%u in ('git remote get-url origin') do set ORIGIN=%%u
git rev-parse --verify origin/%BRANCH% >nul 2>nul
if errorlevel 1 (set NOVA=1) else (set NOVA=)

echo.
echo Pasta:  %CD%
echo Branch: %BRANCH%
echo Origin: %ORIGIN%
echo.
echo Commits que ainda nao estao no GitHub:
if defined NOVA (git log --oneline -10) else (git log --oneline origin/%BRANCH%..%BRANCH%)
echo.

echo %ORIGIN% | find "consulta-precos-scripts" >nul
if not errorlevel 1 (
    echo *** ATENCAO: repositorio PUBLICO. Nao pode subir custo nem margem. ***
    echo.
)

if defined AUTO goto publica
choice /c SN /n /m "Publicar? [S=sim / N=nao] "
if errorlevel 2 (
    echo Cancelado. Nada foi enviado.
    goto fim
)

:publica
echo.
if defined NOVA (git push -u origin %BRANCH%) else (git push origin %BRANCH%)
if errorlevel 1 (
    echo.
    echo ############################################################
    echo #  O PUSH FALHOU. NADA FOI PUBLICADO.
    echo #  Os commits continuam gravados aqui no local.
    echo #  Se o git reclamou de divergencia:  git pull --rebase
    echo ############################################################
    exit /b 1
)
echo.
echo === Publicado em %BRANCH%. ===
:fim
exit /b 0
