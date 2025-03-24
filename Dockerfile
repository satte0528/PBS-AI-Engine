# Use a base Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (including tools for building C extensions)
RUN apt-get update && apt-get install -y \
    build-essential \
    libatlas-base-dev \
    gfortran \
    libssl-dev \
    libffi-dev \
    libopenblas-dev \
    liblapack-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip to the latest version
RUN pip install --upgrade pip

# Copy requirements file into the container
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application
COPY . .

# Expose the port your app will run on
EXPOSE 8000

# Command to run your app (adjust based on your app's start command)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
