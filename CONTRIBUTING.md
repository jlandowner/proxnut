# Contributing to proxnut

This guide covers the essential steps to get started with local development.

## Prerequisites

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/)
- Git
- Docker (for container builds)

## Getting Started

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/jlandowner/proxnut.git
cd proxnut

# Install dependencies with uv
uv sync --locked

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration
```

### 2. Running Locally

```bash
# Run with uv
uv run proxnut
```

### 3. Building Locally

```bash
# Build Docker image
uv run poe build

# Test the Docker build
docker run --env-file .env proxnut:local
```

### 4. Running Tests

Currently, testing is manual. Please verify your changes by:

```bash
# 1. Run the application and verify it starts without errors
uv run proxnut

# 2. Test with different configurations
# Edit .env with different values and test

# 3. Test Docker build and run
docker build -t proxnut:test .
docker run --env-file .env proxnut:test

# 4. Verify logging output
# Check that logs are clear and informative
```
