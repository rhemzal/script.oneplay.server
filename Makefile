# OnePlay Server – provozní targety (spouštět z kořene repozitáře)
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
SCRIPTS := $(ROOT)/scripts
TVH_CONF ?= /home/hts/conf
NOVA_CHANNEL_CONFIG := $(TVH_CONF)/channel/config/acaab01b8661bb155b67bdf93ef8682d

.PHONY: help test health verify tvh-fix tvh-restart verify-tvh

help:
	@echo "OnePlay Server – make targety:"
	@echo "  make test          – pytest"
	@echo "  make health        – curl /health s retry"
	@echo "  make verify        – health + test_nova_hd + test_tvheadend_pipe"
	@echo "  make tvh-fix       – oprava mapování kanálů TVH (sudo)"
	@echo "  make tvh-restart   – tvh-fix + restart tvheadend + health"
	@echo "  make verify-tvh    – ověření Nova HD streamu přes TVH (9981)"

test:
	python3 -m pytest -q

health:
	bash $(SCRIPTS)/check_health.sh

verify: health
	bash $(SCRIPTS)/test_nova_hd.sh
	bash $(SCRIPTS)/test_tvheadend_pipe.sh

tvh-fix:
	sudo env TVH_CONF=$(TVH_CONF) $(SCRIPTS)/fix_tvh_channel_services.sh Oneplay1
	sudo env TVH_CONF=$(TVH_CONF) $(SCRIPTS)/fix_tvh_channel_services.sh

tvh-restart: tvh-fix
	sudo systemctl restart tvheadend
	sleep 10
	bash $(SCRIPTS)/check_health.sh

verify-tvh:
	@python3 -c "import json,sys; d=json.load(open('$(NOVA_CHANNEL_CONFIG)')); s=d.get('services',[]); print('Nova HD services:', s); sys.exit(0 if s else 1)"
	@bytes=$$(curl -s --max-time 10 -o /tmp/oneplay_tvh_nova.ts -w '%{size_download}' \
		"http://127.0.0.1:9981/stream/channelname/Nova%20HD" || true); \
	echo "TVH Nova HD: $$bytes B (10 s sample)"; \
	test "$$bytes" -gt 100000
