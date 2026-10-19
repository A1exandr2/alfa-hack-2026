.PHONY: gitleaks

# Проверить историю Git на секреты: make gitleaks
gitleaks:
	docker run --rm -v "$(CURDIR):/repo:ro" zricethezav/gitleaks:v8.18.2 detect --source=/repo --redact --verbose
