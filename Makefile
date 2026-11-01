.PHONY: require-root dev console test web-build web web-local

# Writable targets require a caller-selected root.
AIHF_ROOT ?=

require-root:
	@test -n "$(AIHF_ROOT)" || { echo "Set AIHF_ROOT to an explicit absolute local root." >&2; exit 2; }
	@python -c "import os,sys; sys.exit(0 if os.path.isabs(sys.argv[1]) else 2)" "$(AIHF_ROOT)" || { echo "AIHF_ROOT must be absolute." >&2; exit 2; }

# Watch and restart the root-bound CLI.
dev: require-root
	mkdir -p "$(AIHF_ROOT)"
	poetry run watchfiles "poetry run aihf --root '$(AIHF_ROOT)'" hedge_fund

# Textual console for interactive development.
console:
	poetry run textual console

test:
	poetry run pytest hedge_fund/

# Build once, then serve synthetic records from a temporary root. The Python
# process serves the packaged static bundle; Node is not needed at request time.
web-build:
	npm --prefix frontend ci
	npm --prefix frontend run build

web:
	$(MAKE) web-build
	poetry run aihf-web --demo

# Read the selected local root. Writes and network remain disabled.
web-local: require-root
	$(MAKE) web-build
	mkdir -p "$(AIHF_ROOT)"
	poetry run aihf-web --root "$(AIHF_ROOT)"
