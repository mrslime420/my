FROM python:3.10-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY main.py .

# ✅ IMPORTANT: Data directory for Railway volume
RUN mkdir -p /data/sms_data

# Railway automatically sets PORT, but bot doesn't need it
# We just need it to keep the service "healthy"
EXPOSE 8080

# Simple HTTP server to keep Railway happy (bypass 15 min sleep)
RUN pip install flask
COPY healthcheck.py .
CMD python main.py & python healthcheck.py
