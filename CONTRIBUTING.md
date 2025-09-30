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

Run the automated unit test suite with Poe:

```bash
uv run poe test
```

Additionally, keep validating behaviour manually when you make changes:

- `uv run proxnut` to exercise the monitoring loop end-to-end.
- Adjust `.env` to cover different UPS and Proxmox configurations.
- `docker build -t proxnut:test .` and `docker run --env-file .env proxnut:test`
  to verify container builds.
- Inspect log output to ensure messages remain clear and actionable.
