#!/usr/bin/env python3
"""
Cloudflare Tunnel Manager

Core API client for managing Cloudflare Tunnels.
"""

import json
import requests
from typing import Dict, List, Optional, Tuple

CF_API_BASE = "https://api.cloudflare.com/client/v4"
CF_ZERO_TRUST_API_BASE = "https://api.cloudflare.com/client/v4/accounts"


class CloudflareTunnelManager:
    """Manages Cloudflare Tunnels via API"""

    def __init__(self, api_token: str, account_id: str):
        self.api_token = api_token
        self.account_id = account_id
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    def _request(
        self, method: str, endpoint: str, data: Optional[Dict] = None
    ) -> Dict:
        url = f"{CF_ZERO_TRUST_API_BASE}/{self.account_id}/{endpoint}"
        response = requests.request(method, url, headers=self.headers, json=data)
        response.raise_for_status()
        result = response.json()

        if not result.get("success", False):
            errors = result.get("errors", [])
            raise Exception(f"Cloudflare API error: {errors}")

        return result

    def get_tunnels(self) -> List[Dict]:
        result = self._request("GET", "cfd_tunnel")
        return result.get("result", [])

    def get_tunnel_by_name(self, name: str) -> Optional[Dict]:
        tunnels = self.get_tunnels()
        return next((t for t in tunnels if t["name"] == name), None)

    def create_tunnel(self, name: str) -> Tuple[str, str]:
        data = {"name": name, "config_src": "local"}
        result = self._request("POST", "cfd_tunnel", data)
        tunnel = result["result"]
        tunnel_id = tunnel["id"]

        token_result = self._request("GET", f"cfd_tunnel/{tunnel_id}/token")
        result_data = token_result.get("result", {})

        if isinstance(result_data, dict):
            tunnel_token = result_data.get("token", "")
        elif isinstance(result_data, str):
            tunnel_token = result_data
        else:
            raise ValueError(f"Unexpected token result format: {type(result_data)}")

        if not tunnel_token:
            raise ValueError("Failed to retrieve tunnel token")

        return tunnel_id, tunnel_token

    def create_route(
        self,
        tunnel_id: str,
        subdomain: str,
        domain: str,
        service_url: str = "http://localhost:5000",
    ) -> Dict:
        try:
            config_result = self._request("GET", f"cfd_tunnel/{tunnel_id}/configurations")
            result_data = config_result.get("result")

            if result_data is None:
                config = {}
            elif isinstance(result_data, str):
                config = json.loads(result_data)
            elif isinstance(result_data, dict):
                config = result_data.get("config", result_data)
                if isinstance(config, str):
                    config = json.loads(config)
                if config is None:
                    config = {}
            else:
                config = {}
        except (json.JSONDecodeError, KeyError, TypeError):
            config = {}

        if config is None:
            config = {}

        ingress = config.get("ingress", [])
        if not isinstance(ingress, list):
            ingress = []

        hostname = f"{subdomain}.{domain}"
        ingress = [r for r in ingress if r.get("hostname") != hostname]

        new_route = {"hostname": hostname, "service": service_url}
        ingress.insert(0, new_route)

        ingress = [r for r in ingress if r.get("service") != "http_status:404"]
        ingress.append({"service": "http_status:404"})

        config["ingress"] = ingress
        data = {"config": config}

        result = self._request("PUT", f"cfd_tunnel/{tunnel_id}/configurations", data)
        return_result = result.get("result", {})
        return return_result if isinstance(return_result, dict) else {}

    def ensure_dns_record(
        self, zone_id: str, subdomain: str, domain: str, tunnel_id: str
    ) -> Dict:
        dns_target = f"{tunnel_id}.cfargotunnel.com"
        records_url = f"{CF_API_BASE}/zones/{zone_id}/dns_records"
        record_name = f"{subdomain}.{domain}"
        params = {"name": record_name, "type": "CNAME"}
        response = requests.get(records_url, headers=self.headers, params=params)
        response.raise_for_status()
        result = response.json()

        if not result.get("success", False):
            errors = result.get("errors", [])
            raise Exception(f"Cloudflare API error getting DNS records: {errors}")

        records = result.get("result", [])

        if records:
            record = records[0]
            record_id = record["id"]
            existing_content = record.get("content", "").rstrip(".")
            dns_target_clean = dns_target.rstrip(".")
            existing_proxied = record.get("proxied", False)

            if existing_content != dns_target_clean or not existing_proxied:
                data = {
                    "name": record_name,
                    "type": "CNAME",
                    "content": dns_target,
                    "ttl": 1,
                    "proxied": True,
                }
                response = requests.put(
                    f"{records_url}/{record_id}", headers=self.headers, json=data
                )
                response.raise_for_status()
                update_result = response.json()
                if not update_result.get("success", False):
                    errors = update_result.get("errors", [])
                    raise Exception(f"Cloudflare API error updating DNS record: {errors}")
                return update_result.get("result", {})
            else:
                return record
        else:
            data = {
                "name": record_name,
                "type": "CNAME",
                "content": dns_target,
                "ttl": 1,
                "proxied": True,
            }
            response = requests.post(records_url, headers=self.headers, json=data)
            response.raise_for_status()
            create_result = response.json()
            if not create_result.get("success", False):
                errors = create_result.get("errors", [])
                raise Exception(f"Cloudflare API error creating DNS record: {errors}")
            return create_result.get("result", {})

    def get_zone_id(self, domain: str) -> str:
        url = f"{CF_API_BASE}/zones"
        params = {"name": domain}
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        zones = response.json().get("result", [])

        if not zones:
            raise Exception(f"Domain {domain} not found in Cloudflare account")

        return zones[0]["id"]
