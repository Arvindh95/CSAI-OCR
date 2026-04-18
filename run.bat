@echo off
set PADDLE_PDX_CACHE_HOME=D:\docling\models\paddlex
set PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
set FLAGS_use_mkldnn=0

cd /d D:\paddleocr
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
