# OnePlay Server – provozní targety (spouštět z kořene repozitáře)
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
SCRIPTS := $(ROOT)/scripts
TVH_CONF ?= /home/hts/conf

.PHONY: help test health verify tvh-fix tvh-restart verify-tvh install-tvh-autofix

help:
	@echo "OnePlay Server – make targety:"
	@echo "  make test                  – pytest"
	@echo "  make health                – curl /health s retry"
	@echo "  make verify                – health + test_nova_hd + test_tvheadend_pipe"
	@echo "  make tvh-fix               – oprava mapování kanálů TVH (sudo)"
	@echo "  make tvh-restart           – ruční tvh-fix + restart + health + verify-tvh"
	@echo "  make verify-tvh            – ověření Nova HD streamu přes TVH (9981)"
	@echo "  make install-tvh-autofix   – systemd drop-in auto tvh-fix po startu TVH (sudo)"

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
	sleep 15
	bash $(SCRIPTS)/check_health.sh
	bash $(SCRIPTS)/verify_tvh_nova.sh

verify-tvh:
	bash $(SCRIPTS)/verify_tvh_nova.sh

install-tvh-autofix:
	sudo bash $(SCRIPTS)/install_tvheadend_auto_fix.sh
