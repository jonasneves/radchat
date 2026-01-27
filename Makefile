.PHONY: help install cli models preview preview-remote stop test setup-tunnel

PORT := 5000
MODEL ?= openai/gpt-4o-mini

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  install         Install dependencies"
	@echo "  cli             Run interactive CLI chat"
	@echo "  models          List available models"
	@echo "  preview         Run local server (http://localhost:$(PORT))"
	@echo "  preview-remote  Run server + ngrok tunnel (HTTPS)"
	@echo "  stop            Stop server and ngrok"
	@echo "  test            Test phone catalog and ACR tools"
	@echo "  setup-tunnel    Setup Cloudflare tunnel"
	@echo ""
	@echo "Environment:"
	@echo "  MODEL=openai/gpt-4o  make cli    Use specific model"

install:
	pip3 install -r requirements.txt

cli:
	MODEL=$(MODEL) python3 -m src.cli

models:
	python3 -m src.cli --models

preview:
	@python3 -m src.server

preview-remote:
	@python3 -m src.server & sleep 2 && ngrok http $(PORT)

stop:
	@pkill -f "python3 -m src.server" 2>/dev/null || true
	@pkill -f "python -m src.server" 2>/dev/null || true
	@pkill -f ngrok 2>/dev/null || true
	@lsof -ti:$(PORT) | xargs kill -9 2>/dev/null || true
	@echo "Stopped"

test:
	@echo "Testing phone directory..."
	python3 -c "from src.tools.phone_catalog import search_contacts; print(search_contacts('CT'))"
	@echo ""
	@echo "Testing ACR criteria..."
	python3 -c "from src.tools.acr_criteria import search_criteria; print(search_criteria('chest'))"

setup-tunnel:
	cd scripts && python3 setup_tunnel.py

clean: stop
