.PHONY: build preview clean new-article new-note new-experiment install

install:
	npm install

build:
	node build.js

preview: build
	npx serve public

clean:
	rm -rf public

# Usage: make new-article SLUG=my-new-post
new-article:
	@test -n "$(SLUG)" || (echo "Usage: make new-article SLUG=my-new-post" && exit 1)
	@mkdir -p content/articles
	@echo '---' > content/articles/$(SLUG).md
	@echo 'title: "$(SLUG)"' >> content/articles/$(SLUG).md
	@echo 'date: $(shell date +%Y-%m-%dT%H:%M:%S%z)' >> content/articles/$(SLUG).md
	@echo 'tags: []' >> content/articles/$(SLUG).md
	@echo '---' >> content/articles/$(SLUG).md
	@echo '' >> content/articles/$(SLUG).md
	@echo "Created content/articles/$(SLUG).md"

# Usage: make new-note SLUG=my-quick-note
new-note:
	@test -n "$(SLUG)" || (echo "Usage: make new-note SLUG=my-quick-note" && exit 1)
	@mkdir -p content/notes
	@echo '---' > content/notes/$(SLUG).md
	@echo 'title: "$(SLUG)"' >> content/notes/$(SLUG).md
	@echo 'date: $(shell date +%Y-%m-%dT%H:%M:%S%z)' >> content/notes/$(SLUG).md
	@echo 'tags: []' >> content/notes/$(SLUG).md
	@echo '---' >> content/notes/$(SLUG).md
	@echo '' >> content/notes/$(SLUG).md
	@echo "Created content/notes/$(SLUG).md"

# Usage: make new-experiment SLUG=my-experiment
new-experiment:
	@test -n "$(SLUG)" || (echo "Usage: make new-experiment SLUG=my-experiment" && exit 1)
	@mkdir -p content/experiments
	@echo '---' > content/experiments/$(SLUG).md
	@echo 'title: "$(SLUG)"' >> content/experiments/$(SLUG).md
	@echo 'date: $(shell date +%Y-%m-%dT%H:%M:%S%z)' >> content/experiments/$(SLUG).md
	@echo 'tags: []' >> content/experiments/$(SLUG).md
	@echo '---' >> content/experiments/$(SLUG).md
	@echo '' >> content/experiments/$(SLUG).md
	@echo "Created content/experiments/$(SLUG).md"
