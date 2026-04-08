@echo off
chcp 65001 > nul
cd /d C:\Users\houmo\sakuraSSAkanri
C:\Users\houmo\AppData\Local\Programs\Python\Python314\python.exe scripts\daily_scrape.py >> instance\logs\task_scheduler.log 2>&1
