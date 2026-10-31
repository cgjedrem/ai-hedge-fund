.PHONY: dev console test web-build web web-local

# The app under Textual's dev tools: app.tcss reloads live, print/log go to
# `make console`, and any change under hedge_fund/ restarts the app.
# watchfiles stops the app with SIGINT first (Textual restores the terminal
# on Ctrl-C), so no signal flag is needed.
dev:
	poetry run watchfiles \
		"poetry run textual run --dev hedge_fund.tui.app:HedgeFundApp" hedge_fund

# Second terminal: the devtools console the running app logs to.
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

# Read the configured local root. Writes and network remain disabled.
web-local:
	$(MAKE) web-build
	poetry run aihf-web
