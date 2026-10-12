"""Point the original frontend at a verified HTTPS cloud backend URL."""
import json
from pathlib import Path
import sys
from urllib.parse import urlparse


def configure(root: Path, backend_url: str) -> None:
    url = urlparse(backend_url)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in {"", "/"}):
        raise ValueError("Use the backend's plain public HTTPS origin URL")
    origin = f"https://{url.netloc}"
    frontend = root / "frontend"
    (frontend / "vercel.json").write_text(json.dumps({
        "framework": "vite", "buildCommand": "npm run build", "outputDirectory": "dist",
        "rewrites": [
            {"source": "/api/:path*", "destination": origin + "/:path*"},
            {"source": "/((?!api(?:/|$)).*)", "destination": "/index.html"},
        ],
    }, indent=2) + "\n")
    env_path = frontend / ".env.production"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    keys = ("VITE_WS_BASE=", "VITE_SPACETIME_ENABLED=")
    lines = [line for line in lines if not line.startswith(keys)]
    lines.extend([f"VITE_WS_BASE=wss://{url.netloc}", "VITE_SPACETIME_ENABLED=false"])
    env_path.write_text("\n".join(lines) + "\n")
    print("Configured original frontend API proxy and secure live socket origin")


if __name__ == "__main__":
    configure(Path(__file__).resolve().parents[1], sys.argv[1])
