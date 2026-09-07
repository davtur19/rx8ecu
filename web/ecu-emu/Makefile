# RX-8 ECU Pin Emulator — build
# Usage: make build   (copies src/ to dist/)
#        make serve   (build + serve on port 8001)
#        make clean   (remove dist/)

SRC = src
DIST = dist
PORT = 8001

.PHONY: build serve clean

build: $(DIST)/index.html $(DIST)/app.js $(DIST)/style.css $(DIST)/pins.json

$(DIST)/index.html: $(SRC)/index.html
	@mkdir -p $(DIST)
	cp $< $@

$(DIST)/app.js: $(SRC)/app.js
	cp $< $@

$(DIST)/style.css: $(SRC)/style.css
	cp $< $@

$(DIST)/pins.json: $(SRC)/pins.json
	cp $< $@

serve: build
	@echo "Serving $(DIST)/ at http://127.0.0.1:$(PORT)/"
	python3 -m http.server $(PORT) --directory $(DIST)

clean:
	rm -rf $(DIST)
