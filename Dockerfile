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

# Create data directory for persistent storage
RUN mkdir -p /data/sms_data

# Railway volume mount path
ENV DATA_DIR=/data/sms_data

# ✅ YEH CHANGE KARO - AUTO MODE KE SAATH
CMD python main.py --auto
