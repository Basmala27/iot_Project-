# Use Python 3.11 image
FROM python:3.11-slim

#  work directory
WORKDIR /app

#  requirements & install
COPY requirements.txt .
paho-mqtt
PyYAML
RUN pip install --no-cache-dir -r requirements.txt

#  code
COPY . .

# Run simulation
CMD ["python", "main.py"]