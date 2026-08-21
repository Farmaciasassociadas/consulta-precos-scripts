@echo off
REM ============================================================
REM  UMA VEZ SO. Apaga custo e margem do HISTORICO do repo publico.
REM  Reescreve os 84 commits: o repositorio cai de 163 MB para ~2 MB.
REM
REM    purgar_historico.bat        -> pede confirmacao
REM    purgar_historico.bat /S     -> sem perguntar (terminal do VS Code)
REM
REM  DEPOIS os outros 2 PCs TEM que re-clonar: todos os SHAs mudam.
REM ============================================================
setlocal
cd /d "%~dp0"
set AUTO=
if /i "%~1"=="/S" set AUTO=1

echo === 1. Conferindo se e seguro ===
for /f %%w in ('git worktree list ^| find /c /v ""') do set WT=%%w
if not "%WT%"=="1" (
    echo ERRO: existe worktree ativa alem da principal. Abortado.
    git worktree list
    echo Feche a sessao e rode: git worktree remove --force ^<caminho^>
    exit /b 1
)
git diff-index --quiet HEAD --
if errorlevel 1 (
    echo ERRO: ha mudancas nao commitadas. Commite ou descarte antes. Abortado.
    git status --short
    exit /b 1
)
for /f "delims=" %%u in ('git remote get-url origin') do set ORIGIN=%%u
echo OK: worktree unica, arvore limpa.
echo Origin: %ORIGIN%
echo.

echo === 2. Backup do historico completo ===
git bundle create "%TEMP%\claude_antes_da_purga.bundle" --all
if errorlevel 1 (echo ERRO no backup. Abortado.& exit /b 1)
echo Backup em: %TEMP%\claude_antes_da_purga.bundle
echo Desfazer tudo:  git clone "%TEMP%\claude_antes_da_purga.bundle" recuperado
echo.
echo Sai do historico (nao apaga copias que terceiros ja baixaram):
type .purgar_dados_paths.txt
echo.

if defined AUTO goto executa
choice /c SN /n /m "Reescrever o historico e forcar o push? [S=sim / N=nao] "
if errorlevel 2 (echo Cancelado. Nada mudou.& exit /b 0)

:executa
echo.
echo === 3. Reescrevendo ===
python -m git_filter_repo --invert-paths --paths-from-file .purgar_dados_paths.txt --force
if errorlevel 1 (
    echo ############################################################
    echo #  A REESCRITA FALHOU. Recupere do bundle antes de mexer.
    echo ############################################################
    exit /b 1
)

echo.
echo === 4. Republicando ===
git remote add origin "%ORIGIN%" 2>nul
git push --force origin master
if errorlevel 1 (
    echo ############################################################
    echo #  O PUSH FALHOU, mas o historico local JA foi reescrito.
    echo #  Rode:  git push --force origin master
    echo ############################################################
    exit /b 1
)

echo.
echo ============================================================
echo  PRONTO. O historico publico nao tem mais custo nem margem.
echo.
echo  AGORA, nos outros 2 PCs (SRVBIG-LJ1 e o terceiro):
echo    1. Salve trabalho nao commitado   2. Apague C:\Claude
echo    3. git clone %ORIGIN% C:\Claude
echo  "git pull" NAO funciona: os SHAs mudaram todos.
echo ============================================================
exit /b 0
