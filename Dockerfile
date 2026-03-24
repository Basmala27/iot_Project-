# Use Python 3.11 image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Copy requirements & install
COPY requirements.txt .
paho-mqtt
PyYAML
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Run simulation
CMD ["python", "main.py"]