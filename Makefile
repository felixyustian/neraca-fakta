# Cek Fakta Saham: common tasks. Run `make dev-api` and `make dev-web` in two terminals.
PY ?= python3

.PHONY: install dev-api dev-web build serve test offline telegram

install:            ## Python + web dependencies
	$(PY) -m pip install -r requirements-dev.txt
	cd web && npm install

dev-api:            ## API with reload on :8000
	$(PY) -m uvicorn cekfakta.api:app --app-dir src --reload --port 8000

dev-web:            ## Vite dev server on :5173 (proxies /api to :8000)
	cd web && npm run dev

build:              ## Production frontend into web/dist (served by the API)
	cd web && npm run build

serve: build        ## One process: API + built frontend on :8000
	$(PY) -m uvicorn cekfakta.api:app --app-dir src --port 8000

offline: build      ## Same as serve, but never calls Sectors (fixtures only, 0 credits)
	DATA_SOURCE=fixtures $(PY) -m uvicorn cekfakta.api:app --app-dir src --port 8000

telegram:           ## Telegram bot (long polling; needs TELEGRAM_BOT_TOKEN in .env)
	PYTHONPATH=src $(PY) -m cekfakta.bot.telegram

test:
	$(PY) -m pytest -q
	cd web && npx tsc -b
