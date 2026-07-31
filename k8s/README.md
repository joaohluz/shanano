# Stage 3: Kubernetes (kind)

Deploys the full Shanano stack — API, worker, PostgreSQL, loadgen, Prometheus, Grafana — on a local [kind](https://kind.sigs.k8s.io/) cluster using plain manifests.

## Prerequisites

- Docker running
- `kind` installed: `brew install kind`
- `kubectl` installed
- `helm` not required (plain manifests)

## Deploy

```bash
# 1. Build the app image (used by api, worker, and loadgen)
docker build -f infra/Dockerfile -t shanano-api:latest .

# 2. Create a single-node kind cluster (config maps NodePorts to localhost)
kind create cluster --name shanano --config k8s/kind-config.yaml

# If you already have a cluster without port mappings, recreate it:
kind delete cluster --name shanano
kind create cluster --name shanano --config k8s/kind-config.yaml

# 3. Load the image into the cluster (kind nodes can't pull it from a registry)
kind load docker-image shanano-api:latest --name shanano

# 4. Apply everything in order
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-configmap.yaml
kubectl apply -f k8s/02-storage.yaml
kubectl apply -f k8s/03-postgres.yaml
kubectl apply -f k8s/04-api.yaml
kubectl apply -f k8s/05-worker.yaml
kubectl apply -f k8s/06-loadgen.yaml
kubectl apply -f k8s/07-prometheus.yaml
kubectl apply -f k8s/08-grafana.yaml
kubectl apply -f k8s/09-pgadmin.yaml

# Or in one shot (order is irrelevant to kube, it resolves dependencies)
kubectl apply -f k8s/

# 5. Watch everything come up
kubectl -n shanano get pods -w
```

## Access

| Service | URL |
|---|---|
| API | `http://localhost:30000` |
| Worker metrics | `http://localhost:30001/metrics` |
| Prometheus | `http://localhost:30900` |
| Grafana | `http://localhost:30030` (admin / shanano) |
| pgAdmin | `http://localhost:30050` (`admin@shanano.dev` / `shanano`) — connect to host `postgres`, port `5432`, user/pass `shanano` |

> If you created the cluster before pgAdmin was added, its NodePort isn't mapped. Use `kubectl -n shanano port-forward svc/pgadmin 5050:80` → `http://localhost:5050`, or recreate the cluster with the updated `kind-config.yaml`.

The loadgen deployment starts hitting the API automatically, so the Grafana dashboard should show the request-rate wave (up, down, up...) within ~2 minutes.

## Useful commands

```bash
kubectl -n shanano get pods,svc,pvc
kubectl -n shanano logs -f deploy/api
kubectl -n shanano logs -f deploy/worker
kubectl -n shanano logs -f deploy/loadgen

# Manually trigger traffic against the API
curl -X POST -F "file=@data/assets/clean_wavs/music-hd-0001.wav" http://localhost:30000/songs/

# Scale the API up/down to watch it affect the dashboard
kubectl -n shanano scale deploy/api --replicas=4

# Tune the loadgen wave from outside
kubectl -n shanano set env deploy/loadgen LOADGEN_MIN_RPS=5 LOADGEN_MAX_RPS=50

# Tear everything down
kind delete cluster --name shanano
```

## Stop / Restart

Three levels of stopping, depending on how long you're done for:

```bash
# 1. Pause the workload but keep the cluster and data (fast, reversible)
kubectl -n shanano scale deploy --all --replicas=0
# resume:
kubectl -n shanano scale deploy --all --replicas=1

# 2. Stop just the fake traffic (keep API/worker/observability running)
kubectl -n shanano scale deploy/loadgen --replicas=0

# 3. Full teardown — deletes the cluster, its containers, and all data
kind delete cluster --name shanano
```

Scaling a deployment to 0 leaves its `StatefulSet`, PVCs, and stored data intact (postgres data, uploaded WAVs, Prometheus TSDB) — pods are just removed. `kind delete cluster` destroys everything: the node container, PVCs, and any data not committed to the repo.

## Notes

- kind only publishes the Kubernetes API port (6443) to the host by default. `k8s/kind-config.yaml` adds `extraPortMappings` so the NodePorts above are reachable on `localhost` — this must be passed at cluster creation time (`--config k8s/kind-config.yaml`); you can't add port mappings to an existing cluster without recreating it.
- `uploads-pvc` and Postgres storage are `ReadWriteOnce`, so API replicas, worker, and Postgres must all schedule onto the same node. This is a safe assumption on a single-node kind cluster. A multi-node cluster would need a `ReadWriteMany` volume (e.g. NFS) for uploads.
- The worker processes uploads serially (one poll loop). If loadgen uploads faster than the worker can fingerprint, `pending` songs accumulate — which is itself a nice thing to watch on the "Songs by Status" panel.
- Prometheus uses `kubernetes_sd_configs` (role: endpoints) to scrape each replica individually. This is why `sum(shanano_..._total)` across the API's 2 replicas is monotonic — scraping a Service instead would round-robin to a random pod each time, making counters bounce up and down. Each pod reset (restart) still drops that pod's counter to 0; use `rate()` for rate panels, which handles resets.
- All Prometheus/Grafana config lives in ConfigMaps, mirroring `observability/` from the Docker-Compose stack.

## Planned (Iteration 4)

- `k8s/10-catalog-cronjob.yaml` — recurring Internet Archive fetch job (mounts `uploads-pvc`, env from configmap + secret) that populates the catalog with metadata-bearing songs for the worker to fingerprint.
- `k8s/secret.yaml` — JWT secret + admin credentials, referenced via `envFrom.secretRef` by api/worker/loadgen/cronjob.
- New configmap keys: `CATALOG_COLLECTION`, `CATALOG_MAX_ITEMS`, `JWT_*`.
- See the full spec in `AGENTS.md` (Iteration 4).
