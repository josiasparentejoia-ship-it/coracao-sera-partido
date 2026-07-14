@echo off
echo ========================================
echo ATUALIZANDO BOT NO DOCKER
echo ========================================
echo.

echo [1/4] Parando container...
docker-compose stop bot
echo.

echo [2/4] Removendo container antigo...
docker-compose rm -f bot
echo.

echo [3/4] Reconstruindo imagem com codigo atualizado...
docker-compose build --no-cache bot
echo.

echo [4/4] Iniciando container novamente...
docker-compose up -d bot
echo.

echo ========================================
echo CONCLUIDO!
echo ========================================
echo.
echo O bot foi atualizado com as correcoes.
echo.
echo Para ver os logs em tempo real:
echo   docker-compose logs -f bot
echo.

pause
