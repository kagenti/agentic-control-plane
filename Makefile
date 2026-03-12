.PHONY: lint fmt test help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Run all pre-commit hooks
	pre-commit run --all-files

fmt: ## Format Python code with ruff
	ruff format .
	ruff check --fix .

test: ## Run tests for all sub-projects
	cd tools/a2a_bridge_server && uv run pytest tests/ -v
	cd agents/k8s_debug_agent && uv run pytest tests/ -v
