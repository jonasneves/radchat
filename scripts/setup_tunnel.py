#!/usr/bin/env python3
"""
Setup Cloudflare Tunnel for RadChat Server
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from cloudflare_tunnel_manager import CloudflareTunnelManager


def _try_add_github_secret(secret_name: str, secret_value: str, repo: str) -> bool:
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return False

        process = subprocess.Popen(
            ["gh", "secret", "set", secret_name, "--repo", repo],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=secret_value, timeout=10)
        return process.returncode == 0

    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False


def main():
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    domain = os.environ.get("TUNNEL_DOMAIN", "neevs.io")
    subdomain = os.environ.get("TUNNEL_SUBDOMAIN", "radchat")
    port = os.environ.get("PORT", "5000")

    if not api_token or not account_id:
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()
            api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
            account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")

    if not api_token or not account_id:
        print("Error: Set CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID")
        sys.exit(1)

    manager = CloudflareTunnelManager(api_token, account_id)
    tunnel_name = "radchat"

    print(f"Setting up tunnel: {tunnel_name}")
    print(f"Endpoint: https://{subdomain}.{domain}")

    existing = manager.get_tunnel_by_name(tunnel_name)

    if existing:
        tunnel_id = existing["id"]
        print(f"Using existing tunnel: {tunnel_id}")
        result = manager._request("GET", f"cfd_tunnel/{tunnel_id}/token")
        result_data = result.get("result", {})
        tunnel_token = result_data.get("token") if isinstance(result_data, dict) else result_data
    else:
        print("Creating new tunnel...")
        tunnel_id, tunnel_token = manager.create_tunnel(tunnel_name)
        print(f"Created tunnel: {tunnel_id}")

    print("Configuring route...")
    manager.create_route(tunnel_id, subdomain, domain, f"http://localhost:{port}")

    print("Setting up DNS...")
    zone_id = manager.get_zone_id(domain)
    manager.ensure_dns_record(zone_id, subdomain, domain, tunnel_id)

    tunnels_file = Path(__file__).parent.parent / "tunnel.json"
    config = {
        "tunnel_id": tunnel_id,
        "tunnel_name": tunnel_name,
        "tunnel_token": tunnel_token,
        "subdomain": subdomain,
        "domain": domain,
        "url": f"https://{subdomain}.{domain}",
        "service_url": f"http://localhost:{port}"
    }

    with open(tunnels_file, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nTunnel configured!")
    print(f"URL: https://{subdomain}.{domain}")
    print(f"Config saved to: {tunnels_file}")

    repo = os.environ.get("GITHUB_REPO", "jonasneves/radchat")
    print(f"\nSetting TUNNEL_TOKEN secret for {repo}...")
    if _try_add_github_secret("TUNNEL_TOKEN", tunnel_token, repo):
        print("TUNNEL_TOKEN secret set successfully")
    else:
        print("Failed to set secret automatically")
        print(f"Run manually: gh secret set TUNNEL_TOKEN --repo {repo}")


if __name__ == "__main__":
    main()
