FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py

ENV HOST=0.0.0.0
ENV PORT=8080
ENV DB_PATH=/data/beacons.sqlite

RUN mkdir -p /data
EXPOSE 8080

CMD ["python", "/app/app.py"]
