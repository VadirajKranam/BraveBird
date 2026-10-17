PYTHON := ./.venv/bin/python
INPUT := inputs/example.json
HEADLESS := true

.PHONY: run resolve install clean

run:
	HEADLESS=$(HEADLESS) $(PYTHON) -m bravebird.cli --input $(INPUT)

resolve:
	$(PYTHON) -m bravebird.resolve_cli --html fixtures/offline/request-form.html --spec fixtures/offline/spec.json

install:
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m playwright install chromium

clean:
	rm -rf runs/latest