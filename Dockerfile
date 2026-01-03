FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SMARTLINK_HOST=0.0.0.0 \
    SMARTLINK_PORT=5000

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libjpeg62-turbo-dev \
        zlib1g-dev \
        libfreetype6-dev \
        libopenjp2-7 \
        libtiff6 \
        libwebp-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY SmartLink.py icon.ico ./

EXPOSE 5000

CMD ["python", "SmartLink.py", "--no-browser", "--no-tray", "--host", "0.0.0.0", "--port", "5000"]
