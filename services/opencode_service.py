import asyncio
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OpenCodeProcess:
    process: asyncio.subprocess.Process
    url: str


class OpenCodeService:

    def __init__(self) -> None:
        self._proc: OpenCodeProcess | None = None
        self._reader_task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.process.returncode is None

    @property
    def url(self) -> str | None:
        return self._proc.url if self._proc else None

    async def start(self) -> str:
        if self.running:
            return f"⚠️ OpenCode is already running at {self.url}"

        process = await asyncio.create_subprocess_exec(
            "opencode", "web",
            "--hostname", "0.0.0.0",
            "--print-logs",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        url = await self._wait_for_url(process)
        if not url:
            self._proc = OpenCodeProcess(process=process, url="unknown")
            self._reader_task = asyncio.create_task(self._reader(process))
            return "⚠️ OpenCode started but could not detect URL."

        self._proc = OpenCodeProcess(process=process, url=url)
        self._reader_task = asyncio.create_task(self._reader(process))
        return f"✅ OpenCode started at {url}"

    async def stop(self) -> str:
        if not self.running:
            return "OpenCode is not running."

        self._proc.process.terminate()
        try:
            await asyncio.wait_for(self._proc.process.wait(), timeout=10)
        except asyncio.TimeoutError:
            self._proc.process.kill()
            await self._proc.process.wait()

        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        self._proc = None
        return "🛑 OpenCode stopped."

    async def _wait_for_url(self, process: asyncio.subprocess.Process) -> str | None:
        url_re = re.compile(r"https?://[^\s]+")
        for _ in range(50):
            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=0.3)
            except asyncio.TimeoutError:
                continue
            if not line:
                return None
            text = line.decode().strip()
            logger.info("opencode: %s", text)
            m = url_re.search(text)
            if m:
                return m.group(0)
        return None

    async def _reader(self, process: asyncio.subprocess.Process) -> None:
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                logger.info("opencode: %s", line.decode().strip())
        except Exception:
            pass
