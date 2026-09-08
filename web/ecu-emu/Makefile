# RX-8 ECU Emulator — build
# Usage: make build   (copies src/ to dist/)
#        make serve   (build + serve on port 8001)
#        make clean   (remove dist/)

SRC = src
DIST = dist
PORT = 8001

.PHONY: build serve clean

build: $(DIST)/index.html $(DIST)/app.js $(DIST)/style.css $(DIST)/pins.json $(DIST)/emu_core.js $(DIST)/engine_sim.js $(DIST)/can_live.js $(DIST)/can_live.css $(DIST)/icons.svg

$(DIST)/index.html: $(SRC)/index.html
	@mkdir -p $(DIST)
	cp $< $@

$(DIST)/app.js: $(SRC)/app.js
	cp $< $@

$(DIST)/style.css: $(SRC)/style.css
	cp $< $@

$(DIST)/pins.json: $(SRC)/pins.json
	cp $< $@

$(DIST)/emu_core.js: $(SRC)/emu_core.js
	cp $< $@

$(DIST)/engine_sim.js: $(SRC)/engine_sim.js
	cp $< $@

$(DIST)/can_live.js: $(SRC)/can_live.js
	cp $< $@

$(DIST)/can_live.css: $(SRC)/can_live.css
	cp $< $@

$(DIST)/icons.svg: $(SRC)/icons.svg
	cp $< $@

serve: build
	@echo "Serving $(DIST)/ at http://127.0.0.1:$(PORT)/"
	python3 -m http.server $(PORT) --directory $(DIST)

clean:
	rm -rf $(DIST)
