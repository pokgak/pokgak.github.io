CLUSTER_NAME = widget-benchmark
N ?= 50

.PHONY: cluster-create cluster-delete build-good build-bad load-good load-bad deploy undeploy setup stress compare logs-good logs-bad clean tidy build-scraper analyze

tidy:
	go mod tidy

build-scraper:
	mkdir -p bin
	go build -o bin/scraper ./cmd/scraper/

analyze:
	@echo "Usage: duckdb -c \".read queries.sql\""
	@echo "Or interactively load a run:"
	@echo "  duckdb"
	@echo "  D CREATE VIEW m AS SELECT * FROM read_csv_auto(['metrics/<run>/metrics-*.csv']);"
	@ls -lt metrics/ 2>/dev/null | head -5 || echo "  No metrics runs yet — run 'make stress' first"

cluster-create:
	kind create cluster --name $(CLUSTER_NAME) --config kind-cluster.yaml

# Feature-gate cluster: same controllers, extra KEPs enabled (ConcurrentWatchObjectDecode, WatchListClient)
cluster-create-fg:
	kind create cluster --name $(CLUSTER_NAME)-fg --config kind-cluster-featuregates.yaml

cluster-delete-fg:
	kind delete cluster --name $(CLUSTER_NAME)-fg

# Full setup for feature-gate run
setup-fg: cluster-create-fg build-good build-good-single load-fg deploy-fg
	@echo "Feature-gate cluster ready. Run 'make stress-good-fg' to benchmark."

load-fg:
	kind load docker-image good-controller:dev --name $(CLUSTER_NAME)-fg
	kind load docker-image good-single-controller:dev --name $(CLUSTER_NAME)-fg

deploy-fg:
	KUBECONFIG=$$(kind get kubeconfig --name $(CLUSTER_NAME)-fg 2>/dev/null) kubectl apply -f config/crd.yaml
	KUBECONFIG=$$(kind get kubeconfig --name $(CLUSTER_NAME)-fg 2>/dev/null) kubectl apply -f config/good/
	sleep 2
	KUBECONFIG=$$(kind get kubeconfig --name $(CLUSTER_NAME)-fg 2>/dev/null) kubectl apply -f config/good/
	KUBECONFIG=$$(kind get kubeconfig --name $(CLUSTER_NAME)-fg 2>/dev/null) kubectl apply -f config/good-single/
	sleep 2
	KUBECONFIG=$$(kind get kubeconfig --name $(CLUSTER_NAME)-fg 2>/dev/null) kubectl apply -f config/good-single/

# Run the good-only 1k-10k benchmark against the feature-gate cluster
stress-good-fg:
	KUBECONFIG=$$(kind get kubeconfig --name $(CLUSTER_NAME)-fg 2>/dev/null) \
	  bash stress-good.sh $(N) 180

cluster-delete:
	kind delete cluster --name $(CLUSTER_NAME)

build-good:
	docker build --build-arg BUILD_CMD=good -t good-controller:dev .

build-bad:
	docker build --build-arg BUILD_CMD=bad -t bad-controller:dev .

load-good:
	kind load docker-image good-controller:dev --name $(CLUSTER_NAME)

load-bad:
	kind load docker-image bad-controller:dev --name $(CLUSTER_NAME)

deploy:
	kubectl apply -f config/crd.yaml
	kubectl apply -f config/good/
	kubectl apply -f config/bad/

undeploy:
	kubectl delete -f config/good/ --ignore-not-found
	kubectl delete -f config/bad/ --ignore-not-found
	kubectl delete -f config/crd.yaml --ignore-not-found

setup: cluster-create build-good build-bad load-good load-bad
	kubectl apply -f config/crd.yaml
	kubectl apply -f config/good/
	sleep 2
	kubectl apply -f config/bad/
	@echo "Cluster ready. Run 'make stress' to start benchmark."

stress:
	bash stress.sh $(N)

# Run at 50, 200, 500, 1000 and print a summary table across scales
stress-scale:
	@for n in 50 200 500 1000; do \
		echo ""; \
		echo "### Scale: $$n widgets ###"; \
		kubectl delete widgets --all -n good --ignore-not-found >/dev/null 2>&1 || true; \
		kubectl delete widgets --all -n bad --ignore-not-found >/dev/null 2>&1 || true; \
		sleep 3; \
		bash stress.sh $$n 60; \
	done

reset-widgets:
	kubectl delete widgets --all -n good --ignore-not-found
	kubectl delete widgets --all -n bad --ignore-not-found

compare:
	bash compare.sh $(N)

logs-good:
	kubectl logs -n good -l app=good-controller --tail=-1

logs-bad:
	kubectl logs -n bad -l app=bad-controller --tail=-1

clean: undeploy cluster-delete
