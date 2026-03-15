# Dockerfile for Yahoo Fantasy Optimizer

# Use official Python lightweight image
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Ensure Python output is sent straight to terminal (logs) without being buffered
ENV PYTHONUNBUFFERED=1

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code
COPY src/ ./src/

# Provide default command to run the optimizer
# Assuming NOTIFICATION_EMAIL is injected as an env var at runtime
CMD ["sh", "-c", "python -m src.main --email-to \"$NOTIFICATION_EMAIL\""]
