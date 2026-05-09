# Use official Python runtime as base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies + Playwright deps
RUN apt-get update && apt-get install -y \
    gcc \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements-cloud.txt .

# Install Python dependencies + Playwright
RUN pip install --no-cache-dir -r requirements-cloud.txt playwright
RUN playwright install chromium

# Copy application code
COPY . .

# Create instance directory for uploads
RUN mkdir -p instance/uploads

# Set environment variables for Cloud Run
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8080

# Run the application with Gunicorn
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 --access-logfile - --error-logfile - run:app
