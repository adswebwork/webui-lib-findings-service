VENV := .venv/bin

.PHONY: db test run fmt clean

db:            ## start Postgres and wait for it to accept connections
	docker compose up -d
	@until docker compose exec -T db pg_isready -U genesis -d findings >/dev/null 2>&1; do sleep 1; done
	@docker compose exec -T db psql -U genesis -d findings -c \
		"SELECT 'findings_test' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='findings_test')\gexec" >/dev/null 2>&1 || true
	@docker compose exec -T db createdb -U genesis findings_test 2>/dev/null || true
	@echo "postgres ready on :55432 (findings, findings_test)"

test: db
	$(VENV)/pytest -q

run: db
	$(VENV)/uvicorn app.main:app --reload --port 8000

clean:
	docker compose down -v
