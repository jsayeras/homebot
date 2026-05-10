import shlex
from typing import Dict, Optional, Set

import docker
import yaml


class DockerService:

    def __init__(self, yaml_path: str = "services.yaml", docker_host: str = "tcp://localhost:2375") -> None:
        self._yaml_path = yaml_path
        self._services: Dict[str, Dict[str, str]] = {}
        self._client = docker.DockerClient(base_url=docker_host)

    def load(self) -> Dict[str, Dict[str, str]]:
        with open(self._yaml_path) as f:
            data = yaml.safe_load(f)
        self._services = data.get("services", {}) if data else {}
        return dict(self._services)

    def _save(self) -> None:
        with open(self._yaml_path, "w") as f:
            yaml.dump({"services": self._services}, f, default_flow_style=False)

    @property
    def services(self) -> Dict[str, Dict[str, str]]:
        if not self._services:
            self.load()
        return dict(self._services)

    def get_tunnel_addr(self, name: str) -> Optional[str]:
        svc = self.services.get(name)
        if svc and svc.get("tunnel"):
            return svc["tunnel"]
        return None

    def get_command(self, name: str) -> Optional[str]:
        svc = self.services.get(name)
        return svc.get("command") if svc else None

    async def running_set(self) -> Set[str]:
        try:
            return set(c.name for c in self._client.containers.list())
        except docker.errors.DockerException as e:
            print(f"[docker] error: {e}")
            return set()

    async def all_containers_set(self) -> Set[str]:
        try:
            return set(c.name for c in self._client.containers.list(all=True))
        except docker.errors.DockerException as e:
            print(f"[docker] error: {e}")
            return set()

    def _container(self, name: str):
        try:
            return self._client.containers.get(name)
        except docker.errors.NotFound:
            return None

    @staticmethod
    def _parse_run_params(params: str) -> tuple[str, dict]:
        tokens = shlex.split(params)
        kwargs = {"detach": True}
        cmd_after_image: list[str] = []
        image = None
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t in ("-d", "--detach"):
                kwargs["detach"] = True
                i += 1
            elif t == "--rm":
                kwargs["auto_remove"] = True
                i += 1
            elif t in ("-it",):
                kwargs["tty"] = True
                kwargs["stdin_open"] = True
                i += 1
            elif t in ("-p", "--publish"):
                i += 1
                if i < len(tokens):
                    parts = tokens[i].split(":")
                    if len(parts) == 2:
                        host_p, cont_p = parts
                        proto = "tcp"
                        kwargs.setdefault("ports", {})[f"{cont_p}/{proto}"] = int(host_p)
                    elif len(parts) == 3:
                        host_ip, host_p, cont_p = parts
                        kwargs.setdefault("ports", {})[f"{cont_p}/tcp"] = (host_ip, int(host_p))
                i += 1
            elif t in ("-v", "--volume"):
                i += 1
                if i < len(tokens):
                    vol = tokens[i]
                    parts = vol.split(":")
                    if len(parts) >= 2:
                        host_path = parts[0]
                        if not host_path.startswith("/"):
                            import os
                            host_path = os.path.abspath(host_path)
                        parts[0] = host_path
                        kwargs.setdefault("volumes", []).append(":".join(parts))
                i += 1
            elif t in ("-e", "--env"):
                i += 1
                if i < len(tokens):
                    kwargs.setdefault("environment", []).append(tokens[i])
                i += 1
            elif t == "--restart":
                i += 1
                if i < len(tokens):
                    kwargs["restart_policy"] = {"Name": tokens[i]}
                i += 1
            elif t == "--name":
                i += 2  # skip, name added by caller
            elif t.startswith("-"):
                i += 2 if i + 1 < len(tokens) and not tokens[i + 1].startswith("-") else 1
            else:
                if image is None:
                    image = t
                else:
                    cmd_after_image.append(t)
                i += 1
        if cmd_after_image:
            kwargs["command"] = " ".join(cmd_after_image)
        return image, kwargs

    async def run(self, name: str) -> str:
        svc = self.services.get(name)
        if svc is None:
            return f"Service '{name}' not found in config."

        params = svc.get("command", "")
        if not params:
            return f"No command defined for '{name}'."

        existing = await self.all_containers_set()
        if name in existing:
            old = self._container(name)
            if old:
                try:
                    old.remove(force=True)
                except docker.errors.DockerException as e:
                    return f"❌ Failed to remove existing container: {e}"

        try:
            image, kwargs = self._parse_run_params(params)
            if image is None:
                return f"❌ Could not parse image from command."
            kwargs.setdefault("name", name)
            self._client.containers.run(image, **kwargs)
            return f"✅ {name} started."
        except docker.errors.DockerException as e:
            return f"❌ {name} failed:\n{e}"
        except Exception as e:
            return f"❌ {name} error:\n{e}"

    async def stop(self, name: str) -> str:
        container = self._container(name)
        if container is None:
            return f"Container '{name}' not found."
        try:
            container.stop(timeout=10)
            return f"🛑 {name} stopped."
        except docker.errors.DockerException as e:
            return f"❌ Failed to stop {name}:\n{e}"

    async def clean(self, name: str) -> str:
        container = self._container(name)
        if container is None:
            return f"Container '{name}' not found."
        try:
            container.remove(force=True)
            return f"🧹 {name} removed."
        except docker.errors.DockerException as e:
            return f"❌ Failed to remove {name}:\n{e}"

    def edit(self, name: str, new_command: str) -> str:
        self.load()
        if name not in self._services:
            return f"Service '{name}' not found in config."
        self._services[name]["command"] = new_command
        self._save()
        return f"✏️ {name} updated."

    def delete(self, name: str) -> str:
        self.load()
        if name not in self._services:
            return f"Service '{name}' not found in config."
        del self._services[name]
        self._save()
        return f"🗑️ {name} removed from config."

    def edit_tunnel(self, name: str, new_addr: str) -> str:
        self.load()
        if name not in self._services:
            return f"Service '{name}' not found in config."
        self._services[name]["tunnel"] = new_addr
        self._save()
        return f"✏️ {name} tunnel updated."

    def delete_tunnel(self, name: str) -> str:
        self.load()
        if name not in self._services:
            return f"Service '{name}' not found in config."
        self._services[name]["tunnel"] = ""
        self._save()
        return f"🗑️ {name} tunnel removed."
