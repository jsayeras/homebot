# Bot — Telegram Server Manager

A Telegram bot that manages Docker containers, Cloudflare tunnels, and services on a remote server through inline keyboard commands.

## Features

- **Docker Service Management** — Start, stop, clean, edit, and delete containers defined in a YAML config
- **Cloudflare Tunnels** — Create ephemeral tunnels (`trycloudflare.com`) for any local service, with or without a config entry
- **OpenCode Web UI** — Start/stop the [opencode](https://opencode.ai) web interface
- **DuckDNS** — Sync public IP and resolve domain
- **Webhook Receiver** — FastAPI endpoint that forwards POST data to your Telegram chat

## Requirements

| Dependency | Purpose |
|---|---|
| Python ≥ 3.12 | Runtime |
| Docker | Container management (via docker-py SDK) |
| [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) | Ephemeral tunnels (`cloudflared tunnel --url`) |
| [opencode](https://opencode.ai) CLI | Web UI server (optional, for the OpenCode feature) |

Python packages (see `pyproject.toml`):
- `python-telegram-bot` — Telegram bot framework
- `docker` — Docker SDK
- `pyyaml` — Config file parsing
- `httpx` — Async HTTP client
- `fastapi` / `uvicorn` — Webhook receiver
- `python-dotenv` — `.env` loading

## Configuration

### Environment Variables

Create a `.env` file in the project root:

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `ALLOWED_CHAT_ID` | Numeric chat ID authorized to use the bot |
| `DUCKDNS_TOKEN` | DuckDNS update token (optional, for DynDNS) |
| `WEBHOOK_SECRET` | Shared secret for webhook auth (optional) |
| `SERVICES_YAML` | Path to services YAML (default: `services.yaml`) |

### Services YAML (`services.yaml`)

Defines Docker services and their optional Cloudflare tunnels:

```yaml
services:
  <name>:
    command: "<docker run parameters as a single CLI string>"
    tunnel: "<host:port>"        # optional, empty string = no tunnel
```

**Example:**

```yaml
services:
  nginx-test:
    command: "-d --rm -p 8080:80 nginx:alpine"
    tunnel: ""
  mealie:
    command: "-d --name mealie -p 9925:9000 -v ./mealie-data:/app/data -e ALLOW_SIGNUP=true --restart unless-stopped ghcr.io/mealie-recipes/mealie:latest"
    tunnel: "localhost:9925"
```

**Supported `command` flags:**

| Flag | Docker SDK equivalent |
|---|---|
| `-d` / `--detach` | `detach=True` |
| `--rm` | `auto_remove=True` |
| `-it` | `tty=True, stdin_open=True` |
| `-p host:container` | `ports={"container/tcp": host}` |
| `-v /host:/container` | `volumes=["/host:/container"]` |
| `-e KEY=val` | `environment=["KEY=val"]` |
| `--restart POLICY` | `restart_policy={"Name": POLICY}` |
| `--name NAME` | Ignored (name is the service key) |

> Note: `--rm` and `--restart` are mutually exclusive in Docker. Do not use both.

Relative volume paths are resolved to absolute paths automatically.

## Usage

```
python bot.py
```

The bot presents an inline keyboard:

```
[ Info ] [ Sync DuckDNS ] [ OpenCode ]
[ Manage Tunnels ] [ Manage Services ]
```

### Manage Services

Lists all services from `services.yaml` with status indicators:
- ✅ — container is running
- 🚇 — Cloudflare tunnel is active for this service

Action buttons per service: 🛑 stop, 🧹 clean (force-remove), ✏️ edit command, 🗑️ delete from config.

Starting a service that has a `tunnel:` configured will also auto-start its Cloudflare tunnel.

### Manage Tunnels

Lists services with a `tunnel:` config plus any manually started tunnels.

Action buttons: 🛑 stop, ✏️ edit address, 🗑️ remove tunnel config.

Supports starting manual tunnels (not in YAML) via "Start Manual Tunnel" — sends `<name> <host>:<port>` as a text message.

### OpenCode

Starts the opencode web UI on a random available port, bound to `0.0.0.0`. Shows the detected URL once running.

### Info

Shows current public IP, DuckDNS resolution, and all active tunnel URLs.

### Webhook

A FastAPI server runs on port 3000. POST to `/webhook?token=<secret>` (or with `Authorization: Bearer <secret>`) to forward arbitrary JSON data to the authorized Telegram chat.

## Architecture

```
bot.py                    — Entry point
bot/
  app.py                  — BotApp: keyboard layout, callback handlers
  config.py               — Config from environment
services/
  docker_service.py       — Docker SDK wrapper, CLI→SDK param parser
  tunnel_service.py       — cloudflared subprocess manager
  opencode_service.py     — opencode web subprocess manager
  webhook_service.py      — FastAPI webhook receiver
  info_service.py         — IP / DNS utilities
services.yaml             — Service definitions
```
