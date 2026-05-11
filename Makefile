IMAGE ?= homebot
TAG ?= latest

GHCR_NAMESPACE ?= ghcr.io/jsayeras
GHCR_IMAGE := $(GHCR_NAMESPACE)/$(IMAGE):$(TAG)

DOCKER_HOST ?= tcp://localhost:2375

.PHONY: build run login push sign verify clean

# -------------------------
# Build image locally
# -------------------------
build:
	docker build -t $(GHCR_IMAGE) .

# -------------------------
# Run container
# -------------------------
run:
	docker run \
		--name $(IMAGE) \
		--network host \
		-e DOCKER_HOST=$(DOCKER_HOST) \
		--mount type=bind,source=./services.yaml,target=/app/services.yaml \
		--env-file .env \
		$(GHCR_IMAGE)

# -------------------------
# Login to GHCR
# -------------------------
login:
	echo $$GITHUB_TOKEN | docker login ghcr.io -u jsayeras --password-stdin

# -------------------------
# Push image (MANDATORY before signing)
# -------------------------
push:
	docker push $(GHCR_IMAGE)

# -------------------------
# Sign image (safe + push-guarded + digest-based)
# -------------------------
sign: push
	@echo "Resolving digest from GHCR..."

	DIGEST=$$(docker buildx imagetools inspect $(GHCR_IMAGE) \
		| awk '/Digest:/ {print $$2; exit}') && \
	if [ -z "$$DIGEST" ]; then \
		echo "ERROR: Could not resolve digest. Image may not exist in GHCR."; \
		exit 1; \
	fi && \
	echo "Signing: $(GHCR_NAMESPACE)/$(IMAGE)@$$DIGEST" && \
	cosign sign $(GHCR_NAMESPACE)/$(IMAGE)@$$DIGEST

# -------------------------
# Verify signature
# -------------------------
verify:
	DIGEST=$$(docker buildx imagetools inspect $(GHCR_IMAGE) \
		| awk '/Digest:/ {print $$2; exit}') && \
	cosign verify $(GHCR_NAMESPACE)/$(IMAGE)@$$DIGEST

# -------------------------
# Cleanup local image
# -------------------------
clean:
	docker rmi $(GHCR_IMAGE) || true
