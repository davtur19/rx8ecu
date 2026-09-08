# RX-8 ECU Emulator — build
# Usage: make build   (copies src/ to dist/)
#        make test    (durable regression suite, node stdlib only)
#        make serve   (build + serve on port 8001)
#        make clean   (remove dist/)

SRC = src
DIST = dist
PORT = 8001

.PHONY: build serve clean test

test:
	node --test tests/

build: $(DIST)/index.html $(DIST)/app.js $(DIST)/style.css $(DIST)/pins.json $(DIST)/emu_core.js $(DIST)/engine_sim.js $(DIST)/can_live.js $(DIST)/audio.js $(DIST)/can_live.css $(DIST)/icons.svg

# B6: single mkdir rule consumed via order-only prerequisites — parallel
# `make -j` no longer races 8 concurrent `mkdir -p` + copy pairs.
$(DIST):
	mkdir -p $(DIST)

$(DIST)/index.html: $(SRC)/index.html | $(DIST)
	cp $< $@

$(DIST)/app.js: $(SRC)/app.js | $(DIST)
	cp $< $@

$(DIST)/style.css: $(SRC)/style.css | $(DIST)
	cp $< $@

$(DIST)/pins.json: $(SRC)/pins.json | $(DIST)
	cp $< $@

$(DIST)/emu_core.js: $(SRC)/emu_core.js | $(DIST)
	cp $< $@

$(DIST)/engine_sim.js: $(SRC)/engine_sim.js | $(DIST)
	cp $< $@

$(DIST)/can_live.js: $(SRC)/can_live.js | $(DIST)
	cp $< $@

$(DIST)/audio.js: $(SRC)/audio.js | $(DIST)
	cp $< $@

$(DIST)/can_live.css: $(SRC)/can_live.css | $(DIST)
	cp $< $@

$(DIST)/icons.svg: $(SRC)/icons.svg | $(DIST)
	cp $< $@

serve: build
	@echo "Serving $(DIST)/ at http://127.0.0.1:$(PORT)/"
	python3 -m http.server $(PORT) --directory $(DIST)

clean:
	rm -rf $(DIST)
