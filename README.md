# proxnut - Proxmox UPS Shutdown Tool

[![Docker Image](https://img.shields.io/badge/docker-ghcr.io%2Fjlandowner%2Fproxnut-blue)](https://ghcr.io/jlandowner/proxnut)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

A Python tool that automatically controls Proxmox VE nodes during power outages
by monitoring UPS status through Network UPS Tools (NUT).

## Features

- 🔌 **UPS Monitoring**: Monitors UPS status via NUT (Network UPS Tools)
- 🖥️ **Proxmox Integration**: Graceful shutdown of specified Proxmox nodes
- ⚙️ **Configurable**: Customizable shutdown delays and target hosts
- 🐳 **Docker Ready**: Available as a Docker container
- ☸️ **Kubernetes Compatible**: Includes Kubernetes deployment manifests

## How It Works

1. **Monitor UPS**: Continuously monitors UPS status through NUT server
2. **Detect Power Loss**: Triggers when UPS status changes from normal (e.g.,
   "OL" - Online)
3. **Shutdown Proxmox Nodes**: Initiates controlled shutdown of specified
   Proxmox nodes
4. **Automatic Recovery**: Resumes monitoring when power is restored

## Prerequisites

### Proxmox Setup

1. **Create API Token**:
   - Go to Datacenter → Permissions → API Tokens
   - Create a new token with appropriate permissions
   - Note the token ID and secret

2. **Required Permissions**:
   - `Sys.PowerMgmt` on nodes you want to shutdown
   - `Sys.Audit` for node status monitoring

### NUT Setup

Ensure your NUT server is configured and accessible:

```bash
# Test NUT connection
upsc your-ups-name@nut-server-ip
```

## Installation

### Using UV

```bash
# Clone the repository
git clone https://github.com/jlandowner/proxnut.git
cd proxnut

# Prepare .env file
cp .env.example .env
# Edit .env with your configuration

# Run
uv run proxnut
```

### Using Docker

```bash
# Prepare .env file
cp .env.example .env
# Edit .env with your configuration

# Run container
docker run -d --name proxnut --env-file .env ghcr.io/jlandowner/proxnut:latest
```

### Using Kubernetes

```bash
# Prepare .env config map
# Edit deploy/k8s.yaml with your configuration

# Apply the manifests
kubectl apply -f deploy/k8s.yaml
```

## Configuration

### Environment Variables

| Variable                 | Description                           | Default       |
| ------------------------ | ------------------------------------- | ------------- |
| `PROXMOX_HOST`           | Proxmox server hostname               | `localhost`   |
| `PROXMOX_PORT`           | Proxmox API port                      | `8006`        |
| `PROXMOX_VERIFY_TLS`     | Verify TLS certificates               | `true`        |
| `PROXMOX_USER`           | Proxmox user for API access           | `example@pam` |
| `PROXMOX_TOKEN_NAME`     | API token name                        | `proxnut`     |
| `PROXMOX_TOKEN`          | API token value                       | Required      |
| `NUT_HOST`               | NUT server hostname                   | `127.0.0.1`   |
| `NUT_PORT`               | NUT server port                       | `3493`        |
| `NUT_UPS_NAME`           | UPS name in NUT                       | Required      |
| `UPS_NORMAL_STATUSES`    | Normal UPS statuses (comma-separated) | `OL,OL CHRG`  |
| `PROXNUT_SHUTDOWN_HOSTS` | Target hosts to shutdown              | Required      |
| `CHECK_INTERVAL`         | Status check interval in seconds      | `5`           |

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file
for details.

## Acknowledgments

- [Network UPS Tools (NUT)](https://networkupstools.org/) for UPS monitoring
  - [PyNUTClient](https://github.com/networkupstools/nut/tree/master/scripts/python/module)
    for Python NUT client
- [Proxmox VE](https://www.proxmox.com/) for the virtualization platform
  - [proxmoxer](https://github.com/proxmoxer/proxmoxer) for Proxmox API client
