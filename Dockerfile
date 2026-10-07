FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose Coordinator & Dashboard port
EXPOSE 8000

ENV PORT=8000
ENV PYTHONUNBUFFERED=1

# Default entrypoint runs the full simulation testbed
CMD ["python", "run_simulation.py"]
