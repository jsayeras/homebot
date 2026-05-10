import asyncio
import re
from typing import Dict, Optional


class TunnelInfo:
    def __init__(self, name: str, host: str, port: int) -> None:
        self.name = name
        self.host = host
        self.port = port
        self.process: Optional[asyncio.subprocess.Process] = None
        self.url: Optional[str] = None
        self._reader_task: Optional[asyncio.Task] = None


class TunnelService:

    def __init__(self) -> None:
        self._tunnels: Dict[str, TunnelInfo] = {}

    def _get_free_name(self, base: str = "tunnel") -> str:
        if base not in self._tunnels:
            return base
        i = 1
        while f"{base}-{i}" in self._tunnels:
            i += 1
        return f"{base}-{i}"

    async def start(self, name: str, host: str = "localhost", port: int = 3000) -> str:
        if name in self._tunnels:
            info = self._tunnels[name]
            if info.process is not None and info.process.returncode is None:
                return f"Already running: {name} -> {info.url}"

        name = self._get_free_name(name)
        info = TunnelInfo(name, host, port)
        cmd = ["cloudflared", "tunnel", "--url", f"http://{host}:{port}"]

        try:
            info.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            return "cloudflared not found. Install it first."

        self._tunnels[name] = info
        info._reader_task = asyncio.create_task(self._read_output(info))

        for _ in range(50):
            if info.url:
                return info.url
            await asyncio.sleep(0.2)

        return f"{name}: tunnel started, waiting for URL..."

    async def stop(self, name: str) -> str:
        info = self._tunnels.get(name)
        if info is None:
            return f"No tunnel named '{name}'."

        if info.process and info.process.returncode is None:
            if info._reader_task:
                info._reader_task.cancel()
                try:
                    await info._reader_task
                except asyncio.CancelledError:
                    pass
            info.process.terminate()
            try:
                await asyncio.wait_for(info.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                info.process.kill()
                await info.process.wait()

        del self._tunnels[name]
        return f"Tunnel '{name}' stopped."

    async def stop_all(self) -> str:
        if not self._tunnels:
            return "No tunnels running."
        names = list(self._tunnels.keys())
        for name in names:
            await self.stop(name)
        return f"Stopped {len(names)} tunnel(s)."

    def get(self, name: str) -> Optional[TunnelInfo]:
        return self._tunnels.get(name)

    @property
    def running(self) -> Dict[str, TunnelInfo]:
        return {
            n: t for n, t in self._tunnels.items()
            if t.process is not None and t.process.returncode is None
        }

    @property
    def is_running(self) -> bool:
        return any(
            t.process is not None and t.process.returncode is None
            for t in self._tunnels.values()
        )

    async def _read_output(self, info: TunnelInfo) -> None:
        try:
            async for line in info.process.stdout:
                decoded = line.decode(errors="replace").strip()
                print(f"[cloudflared {info.name}] {decoded}")
                url = self._extract_url(decoded)
                if url:
                    info.url = url
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _extract_url(text: str) -> Optional[str]:
        m = re.search(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com", text)
        return m.group(0) if m else None
