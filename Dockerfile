# syntax=docker/dockerfile:1
# 多云产品信息一站式检索平台 —— 零第三方依赖镜像
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MCS_HOST=0.0.0.0 \
    MCS_PORT=8787

WORKDIR /app

# 仅拷贝运行所需内容（无 pip install，无外部依赖）
COPY core/ /app/core/
COPY data/ /app/data/
COPY server/ /app/server/
COPY web/ /app/web/
COPY mcp/ /app/mcp/
COPY tools/ /app/tools/
COPY cli.py /app/cli.py

# 以非 root 运行
RUN useradd -r -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('MCS_PORT','8787')+'/api/health',timeout=3).status==200 else 1)"

CMD ["python3", "server/app.py"]
