FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for PyAV and MySQL
RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure storage directories exist
RUN mkdir -p storage/uploads storage/downloads storage/clips

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
