FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# Three.js للمعاينة ثلاثية الأبعاد؛ فشله ما يوقف البناء
RUN python -m app.vendor_fetch || true
RUN useradd -m -u 1000 rd && mkdir -p /app/data && chown -R rd /app
USER rd
ENV RD_DATA_DIR=/app/data
EXPOSE 8765
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
