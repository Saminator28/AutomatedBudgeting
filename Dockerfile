FROM python:3.12-slim

# Install system dependencies for PDF, OCR, ML libraries, and Node.js for React
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model
RUN python -m spacy download en_core_web_sm

# Copy application code
COPY . .

# Build React dashboard
WORKDIR /app/src/ui
RUN npm install && npm run build

# Back to app root
WORKDIR /app

# Copy and set entrypoint script as executable
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Create necessary directories
RUN mkdir -p statements monthly_reports logs

# Expose FastAPI port
EXPOSE 8000

# Use entrypoint for setup, then run uvicorn
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "src.ui.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
