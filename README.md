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
| `DOCKER_HOST` | Docker daemon URL (default: `tcp://localhost:2375`) |

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

### Local

```
python bot.py
```

### Docker

#### Using Makefile

```
make build          # build the image
make run            # run the container (add DOCKER_HOST=... if needed)
make publish        # push to a registry (set REGISTRY=...)
make sign           # cosign the image
```

#### Or directly with docker

Build:

```
docker build -t bot .
```

Run:

```
docker run -d \
  --name bot \
  --restart unless-stopped \
  --network host \
  --env-file .env \
  -e DOCKER_HOST=tcp://localhost:2375 \
  bot
```

Environment:
- `.env` — bot configuration (token, chat ID, etc.) loaded via `--env-file`

The bot connects to Docker via TCP at `DOCKER_HOST` (default `tcp://localhost:2375`). Using `--network host` ensures `localhost` inside the container resolves to the host machine.

### Docker TCP Setup

By default the Docker daemon only listens on a Unix socket (`/var/run/docker.sock`). Since the bot runs inside a container without the socket mounted, Docker must also listen on TCP.

Run `setup-docker.sh` to configure this:

```
sudo ./setup-docker.sh
```

The script detects whether Docker uses **systemd socket activation** or a plain daemon.json config, then applies the correct method:

- **systemd mode** — creates an override at `/etc/systemd/system/docker.service.d/override.conf` that adds `-H tcp://127.0.0.1:2375` to the dockerd command
- **daemon.json mode** — adds a `hosts` entry with both the Unix socket and TCP address

After running the script, Docker will listen on `tcp://127.0.0.1:2375` in addition to the default Unix socket.

**Security benefits of this approach over mounting `/var/run/docker.sock`:**

- **No filesystem exposure** — Mounting the Docker socket into a container grants that container full access to the host's Docker API. If the bot is compromised, an attacker cannot use the socket to escalate privileges or access other host resources.
- **Loopback-only binding** — The daemon listens on `127.0.0.1:2375`, so the TCP port is only reachable from the host itself (not from the network). Combined with `--network host`, only co-located containers can connect.
- **Non-root container** — The bot runs as an unprivileged `app` user. Even with Docker API access, the attacker must first escape the container's user context.
- **Explicit connection** — The bot connects to a known TCP address rather than depending on file permissions of a shared socket. This makes the access boundary clear and auditable.

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

> **WIP** — This feature is a work in progress.

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
