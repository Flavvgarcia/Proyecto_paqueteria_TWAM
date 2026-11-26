FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8004
# gunicorn: servidor de producción (varios procesos). Su configuración está en gunicorn.conf.py
CMD ["gunicorn", "app:app"]