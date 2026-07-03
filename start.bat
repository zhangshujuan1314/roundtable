@echo off
chcp 65001 >nul 2>&1
echo.
echo   ◉ Roundtable — 多模型圆桌决策
echo.
python -m web.app %*
pause
