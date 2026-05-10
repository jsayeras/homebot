IMAGE ?= bot
TAG ?= latest
REGISTRY ?=
DOCKER_HOST ?= tcp://localhost:2375

FULL_IMAGE := $(if $(REGISTRY),$(REGISTRY)/,)$(IMAGE):$(TAG)

.PHONY: build run sign publish

build:
	docker build -t $(FULL_IMAGE) .

run:
	docker run --rm \
		--name bot \
		--network host \
		-e DOCKER_HOST=$(DOCKER_HOST) \
		-v .env:/app/.env \
		$(FULL_IMAGE)

publish:
	docker push $(FULL_IMAGE)

sign:
	cosign sign $(FULL_IMAGE)
