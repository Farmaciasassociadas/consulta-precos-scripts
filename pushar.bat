@echo off
REM Publica os commits locais no GitHub. Existe porque o push a partir do
REM Claude Code cai no classificador de permissoes; aqui quem dispara e voce.
REM
REM Use tambem no repo PRIVADO do app:  pushar.bat C:\Users\docze\ConsultaPrecosEAN
setlocal
if not "%~1"=="" (cd /d "%~1") else (cd /d "%~dp0")

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
echo Arquivos que serao publicados:
if not defined NOVA git diff --stat origin/%BRANCH%..%BRANCH%
echo.

echo %ORIGIN% | find "consulta-precos-scripts" >nul
if not errorlevel 1 (
    echo *** ATENCAO: este repositorio e PUBLICO. ***
    echo *** Confira acima se nao ha custo, margem ou preco no lote. ***
    echo.
)

choice /c SN /n /m "Publicar? [S=sim / N=nao] "
if errorlevel 2 (
    echo Cancelado. Nada foi enviado.
    goto fim
)

echo.
if defined NOVA (git push -u origin %BRANCH%) else (git push origin %BRANCH%)
if errorlevel 1 (
    echo.
    echo FALHOU. Nenhum commit foi perdido: continuam gravados aqui no local.
    echo Se o git reclamou de divergencia:  git pull --rebase
) else (
    echo.
    echo Publicado em %BRANCH%.
)

:fim
echo.
pause
