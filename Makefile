.PHONY: up down logs agent

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

agent:
	@echo "Run the agent locally (requires Crystal):"
	@echo "  crystal run src/agent.cr -- --url http://127.0.0.1:8080/ingest --interval 15 --jitter 3 --tag env=lab"
