@echo off
REM ============================================================
REM  UMA VEZ SO. Apaga custo e margem do HISTORICO do repo publico.
REM
REM  Reescreve os 83 commits: o repositorio cai de 163 MB para 1.6 MB.
REM  Testado em clone descartavel -- a arvore atual fica identica, so o
REM  historico perde os 22 arquivos de dados.
REM
REM  DEPOIS DISSO os outros 2 PCs TEM que re-clonar. Os SHAs mudam todos;
REM  um "git pull" la vai dar conflito irreconciliavel.
REM ============================================================
setlocal
cd /d "%~dp0"

echo === 1. Conferindo se e seguro ===

for /f %%w in ('git worktree list ^| find /c /v ""') do set WT=%%w
if not "%WT%"=="1" (
    echo ERRO: existe worktree ativa alem da principal.
    git worktree list
    echo.
    echo Provavelmente e outra sessao do Claude Code trabalhando neste repo.
    echo Reescrever o historico agora destruiria o trabalho dela.
    echo Feche a sessao, rode "git worktree prune" e tente de novo.
    goto fim
)

git diff-index --quiet HEAD --
if errorlevel 1 (
    echo ERRO: ha mudancas nao commitadas. Commite ou guarde antes.
    git status --short
    goto fim
)

for /f "delims=" %%u in ('git remote get-url origin') do set ORIGIN=%%u
echo Worktree unica, arvore limpa. Origin: %ORIGIN%
echo.

echo === 2. Backup do historico completo ===
git bundle create "%TEMP%\claude_antes_da_purga.bundle" --all
if errorlevel 1 goto fim
echo Backup: %TEMP%\claude_antes_da_purga.bundle
echo Para desfazer tudo:  git clone "%TEMP%\claude_antes_da_purga.bundle" recuperado
echo.

echo === 3. O que sai do historico ===
type .purgar_dados_paths.txt
echo.
echo Isto NAO apaga copias que terceiros ja tenham baixado do GitHub.
echo.

choice /c SN /n /m "Reescrever o historico e forcar o push? [S=sim / N=nao] "
if errorlevel 2 (
    echo Cancelado. Nada mudou.
    goto fim
)

echo.
echo === 4. Reescrevendo ===
python -m git_filter_repo --invert-paths --paths-from-file .purgar_dados_paths.txt --force
if errorlevel 1 (
    echo FALHOU. O repositorio local pode estar em estado intermediario.
    echo Recupere do bundle acima antes de mexer em qualquer coisa.
    goto fim
)

echo.
echo === 5. Republicando ===
git remote add origin "%ORIGIN%" 2>nul
git push --force origin master
if errorlevel 1 (
    echo.
    echo O push falhou. O historico local JA foi reescrito.
    echo Rode manualmente:  git push --force origin master
    goto fim
)

echo.
echo ============================================================
echo  Pronto. O historico publico nao tem mais custo nem margem.
echo.
echo  AGORA, nos outros 2 PCs (SRVBIG-LJ1 e o terceiro):
echo    1. Salve qualquer trabalho nao commitado
echo    2. Apague a pasta C:\Claude
echo    3. git clone %ORIGIN% C:\Claude
echo  Um "git pull" NAO funciona: os SHAs mudaram todos.
echo.
echo  Os dados continuam sincronizando, pelo repo PRIVADO do app.
echo ============================================================

:fim
echo.
pause
