*Emil Nabiullin, e.nabiullin@innopolis.university*
---
# Lab 2 — Containerization: Inspect, Understand, Optimize

## Task 1 — Docker Inspection & Operations

### 2.1 Image Inspection
**Docker images:**
(app-events, app-gateway, app-payments - вставьте вывод docker images | grep app)
**Gateway image layers analysis:**
```
CREATED BY SIZE
CMD ["uvicorn" "main:app" "--host" "0.0.0.0"… 0B
EXPOSE map[8081/tcp:{}] 0B
COPY main.py . # buildkit 20.5kB
RUN /bin/sh -c pip install --no-cache-dir -r… 43.6MB
COPY requirements.txt . # buildkit 12.3kB
WORKDIR /app 8.19kB
CMD ["python3"] 0B
RUN /bin/sh -c set -eux; for src in idle3 p… 16.4kB
RUN /bin/sh -c set -eux; savedAptMark="$(a… 40.2MB
ENV PYTHON_SHA256=639e43243c620a308f968213df… 0B
ENV PYTHON_VERSION=3.13.14 0B
ENV GPG_KEY=7169605F62C751356D054A26A821E680… 0B
RUN /bin/sh -c set -eux; apt-get update; a… 4.94MB
ENV PATH=/usr/local/bin:/usr/local/sbin:/usr… 0B
# debian.sh --arch 'amd64' out/ 'trixie' '@1… 87.4MB
```
**Analysis:**
- **Number of layers:** 15 layers
- **Largest layer:** 87.4MB (Debian base image - `debian.sh`)
- **Second largest:** 43.6MB (pip install dependencies)
- **Why pip install is large:** Because `requirements.txt` includes FastAPI, uvicorn, httpx, redis, asyncpg and their dependencies

### 2.2 Container Inspection

**IP addresses:**
- events: `172.22.0.5`
- gateway: `172.22.0.6`
- payments: `172.22.0.4`

**Payments environment variables:**
```
PAYMENT_FAILURE_RATE=0.0
PAYMENT_LATENCY_MS=0
PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
GPG_KEY=7169605F62C751356D054A26A821E680E5FA6305
PYTHON_VERSION=3.13.14
PYTHON_SHA256=639e43243c620a308f968213df9e00f2f8f62332f7adbaa7a7eeb9783057c690
```
### 2.3 Live Debugging with exec

**whoami output:** `root`

**id output:** `uid=0(root) gid=0(root) groups=0(root)`

**DNS configuration (/etc/resolv.conf):**
```
nameserver 127.0.0.11
options ndots:0
```
**Gateway → events health check:**
```json
{"status":"healthy","checks":{"postgres":"ok","redis":"ok"}}
```
**Gateway → payments health check:**
```json
{"status":"healthy","failure_rate":0.0,"latency_ms":0}
```
### 2.4 Logs Analysis
**Logs after generating traffic:**
```
events-1    | 2026-06-11T10:26:24.474... {"msg":"Reserved 1 tickets for event 1: f1d3f156-878c-4dd2-9d3b-4d50023b5f7c"}
events-1    | 2026-06-11T10:26:24.476... "POST /events/1/reserve HTTP/1.1" 200 OK
gateway-1   | 2026-06-11T10:26:24.476... "HTTP Request: POST http://events:8081/events/1/reserve" 200 OK
```
**Can you follow a request across services?**
- Yes. By matching timestamps, you can trace a request from gateway → events. For example, the reservation request at 10:26:24.476 appears in both gateway and events logs with the same reservation_id.

### 2.5 Network Inspection
**Network name:** `app_default` (bridge driver)

**Containers in network:**
```
app-gateway-1: 172.22.0.6
app-events-1: 172.22.0.5
app-payments-1: 172.22.0.4
app-redis-1: 172.22.0.3
app-postgres-1: 172.22.0.2
```
### 2.6 Service Discovery
**How does the gateway find the events service?**

- Gateway uses Docker's embedded DNS server at 127.0.0.11. When the gateway makes a request to http://events:8081, Docker DNS automatically resolves the hostname events to the container IP address of the service named events in the same Docker network.

**What IP does events resolve to?**

- events resolves to 172.22.0.5 (from docker network inspect)

**How it works:**

1. Docker Compose creates a custom bridge network (app_default)
2. Each container is added with its service name as a DNS entry
3. Containers can communicate using service names instead of IP addresses
4. This provides automatic service discovery without hardcoding IPs

## Task 2 — Dockerfile Optimization

### 2.7 .dockerignore

**.dockerignore content (same for all services):**
```
__pycache__
*.pyc
*.pyo
*.pyd
.git
.gitignore
.env
.venv
venv/
*.md
.vscode
.idea
Dockerfile
.dockerignore
```

**Image sizes comparison:**

| Service | Before | After | Change |
|---------|--------|-------|--------|
| app-gateway | 214MB | 215MB | +1MB |
| app-events | 233MB | 234MB | +1MB |
| app-payments | 212MB | 213MB | +1MB |

**Analysis:** 
- `.dockerignore` had minimal impact on image size because the build context was already clean
- The 1MB increase is due to the added layers for non-root user creation
- Main benefit of `.dockerignore` is preventing accidental inclusion of sensitive files (`.env`, `.git`, etc.)

### 2.8 Non-Root User

**Dockerfile changes (diff):**
```diff
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

+ # Create non-root user
+ RUN addgroup --system app && adduser --system --ingroup app app
+ RUN chown -R app:app /app
+ USER app

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```
**Verification:**
```bash
$ docker exec app-gateway-1 whoami
app

$ docker exec app-gateway-1 id
uid=100(app) gid=101(app) groups=101(app)
```
**Health check still working:**
```json
{
    "status": "healthy",
    "checks": {
        "events": "ok",
        "payments": "ok",
        "circuit_payments": "CLOSED"
    }
}
```

**Security improvement:**

- **Before**: Container ran as root (UID 0) - any compromise gives full host access
- **After**: Container runs as app (UID 100) - limited permissions, follows principle of least privilege
- The `chown -R app:app /app` ensures the app user can write to the application directory if needed

**Dockerfile content after optimization (gateway):**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN addgroup --system app && adduser --system --ingroup app app
RUN chown -R app:app /app
USER app

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```
