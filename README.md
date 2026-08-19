---
title: Hermes Container Preconfig
emoji: ⚕️
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---
# Lệnh:
# Hermes Container - Build, Run & Test

## 1. Di chuyển vào thư mục project

```bash
cd ~/hermes-container-preconfig
```

## 2. Kiểm tra cấu trúc project

```bash
ls -la
```

Kiểm tra Docker Compose:

```bash
cat docker-compose.yml
```

---

# 3. Dừng container cũ

```bash
docker compose down
```

Kiểm tra:

```bash
docker compose ps -a
```

---

# 4. Build Docker image

## Build thông thường

```bash
docker compose build
```

## Build sạch hoàn toàn, không sử dụng cache

Khuyến nghị sử dụng sau khi sửa `Dockerfile`, `install.sh`, `entrypoint.sh` hoặc dependency:

```bash
docker compose build --no-cache
```

---

# 5. Khởi chạy container

```bash
docker compose up -d
```

---

# 6. Kiểm tra trạng thái container

```bash
docker compose ps
```

Hoặc:

```bash
docker ps
```

Container cần có trạng thái tương tự:

```text
Up ...
0.0.0.0:7860->7860/tcp
```

---

# 7. Xem logs

## Xem toàn bộ logs hiện tại

```bash
docker compose logs
```

## Xem logs realtime

```bash
docker compose logs -f
```

## Xem trực tiếp container Hermes

```bash
docker logs -f hermes-test
```

## Xem 100 dòng cuối và tiếp tục theo dõi

```bash
docker logs --tail 100 -f hermes-test
```

Thoát chế độ xem logs bằng:

```text
Ctrl + C
```

`Ctrl + C` chỉ thoát xem logs, không dừng container.

---

# 8. Kiểm tra Web Terminal

Mở trình duyệt:

```text
http://localhost:7860
```

---

# Test lại hoàn toàn từ đầu

Sử dụng quy trình này sau khi sửa code quan trọng.

## 1. Vào project

```bash
cd ~/hermes-container-preconfig
```

## 2. Dừng container

```bash
docker compose down
```

## 3. Build lại không dùng cache

```bash
docker compose build --no-cache
```

## 4. Khởi chạy

```bash
docker compose up -d
```

## 5. Kiểm tra container

```bash
docker compose ps
```

## 6. Xem logs realtime

```bash
docker logs --tail 100 -f hermes-test
```

---

# Kiểm tra Hermes bên trong container

Mở shell trong container:

```bash
docker exec -it hermes-test bash
```

Sau đó:

```bash
export HERMES_HOME=/data/hermes
export PATH=/data/hermes/bin:/data/hermes/node/bin:/data/hermes/hermes-agent/venv/bin:$PATH
```

## Kiểm tra process Hermes

```bash
ps aux | grep -E 'hermes|screen' | grep -v grep
```

## Kiểm tra screen

```bash
screen -ls
```

## Kiểm tra Hermes

```bash
hermes status
```

---

# Kiểm tra Node.js và npm

Chạy từ máy host:

```bash
docker exec -it hermes-test bash -lc '
echo "=== NODE ==="
which node || true
node --version || true

echo
echo "=== NPM ==="
which npm || true
npm --version || true

echo
echo "=== NPX ==="
which npx || true
npx --version || true

echo
echo "=== PATH ==="
echo "$PATH"
'
```

Kết quả mong muốn:

```text
=== NODE ===
.../node
v26.x.x

=== NPM ===
.../npm
11.x.x

=== NPX ===
.../npx
11.x.x
```

---

# Kiểm tra vị trí Node.js và npm

```bash
docker exec -it hermes-test bash -lc '
echo "=== HOME ==="
echo "$HOME"

echo
echo "=== HERMES NODE FILES ==="
find /data/hermes /root/.hermes \
  -maxdepth 5 \
  -type f \
  \( -name node -o -name npm -o -name npx \) \
  -print 2>/dev/null
'
```

---

# Kiểm tra cấu hình Hermes

```bash
docker exec -it hermes-test bash -lc '
export HERMES_HOME=/data/hermes
export PATH=/data/hermes/bin:/data/hermes/node/bin:/data/hermes/hermes-agent/venv/bin:$PATH

echo "=== CONFIG FILES ==="
find /data/hermes -maxdepth 2 -type f \
  \( -name "*.yaml" -o -name "*.yml" -o -name "*.json" -o -name ".env" \) \
  -print

echo
echo "=== .env ==="
cat /data/hermes/.env

echo
echo "=== config.yaml ==="
cat /data/hermes/config.yaml 2>/dev/null || true
'
```

---

# Kiểm tra API Key và Model

Không in API key đầy đủ ra terminal.

Sử dụng:

```bash
docker exec -it hermes-test bash -lc '
export HERMES_HOME=/data/hermes
export PATH=/data/hermes/bin:/data/hermes/node/bin:/data/hermes/hermes-agent/venv/bin:$PATH

hermes status
'
```

Cần kiểm tra các dòng:

```text
Model: <model-name>
Provider: OpenRouter
```

và:

```text
OpenRouter    ✓
```

---

# Kiểm tra config model

```bash
docker exec -it hermes-test bash -lc '
export HERMES_HOME=/data/hermes

echo "=== config.yaml ==="
cat /data/hermes/config.yaml 2>/dev/null || true

echo
echo "=== .env keys ==="
grep -E "^[A-Z0-9_]+=" /data/hermes/.env 2>/dev/null \
  | sed "s/=.*/=<configured>/"
'
```

---

# Nếu sửa code rồi muốn rebuild nhanh

```bash
cd ~/hermes-container-preconfig

docker compose down

docker compose build --no-cache

docker compose up -d

docker compose ps

docker logs --tail 100 -f hermes-test
```

---

# Nếu container không khởi động

Kiểm tra:

```bash
docker compose ps -a
```

Sau đó:

```bash
docker compose logs --tail 200
```

Hoặc:

```bash
docker logs --tail 200 hermes-test
```

Kiểm tra Docker events:

```bash
docker events --since 10m
```

---

# Nếu muốn xóa container và build lại

```bash
cd ~/hermes-container-preconfig

docker compose down

docker compose rm -f

docker compose build --no-cache

docker compose up -d

docker compose ps

docker logs --tail 100 -f hermes-test
```

---

# Xóa cả image để test sạch

Chỉ sử dụng khi thực sự cần:

```bash
cd ~/hermes-container-preconfig

docker compose down --rmi all

docker compose build --no-cache

docker compose up -d

docker compose ps

docker logs --tail 100 -f hermes-test
```

---

# Kiểm tra Docker resources của project

## Container

```bash
docker ps -a --filter "name=hermes"
```

## Image

```bash
docker images | grep -i hermes
```

## Volume

```bash
docker volume ls | grep -i hermes
```

## Network

```bash
docker network ls | grep -i hermes
```

---

# Quy trình test khuyến nghị sau mỗi lần AI sửa code

```bash
cd ~/hermes-container-preconfig

docker compose down

docker compose build --no-cache

docker compose up -d

docker compose ps

docker logs --tail 200 -f hermes-test
```

Sau khi logs xuất hiện:

```text
Uvicorn running on http://0.0.0.0:7860
```

mở trình duyệt:

```text
http://localhost:7860
```

Sau đó kiểm tra:

1. Web Terminal có hoạt động không.
2. Hermes Agent có chạy trong `screen` không.
3. `hermes status` có nhận OpenRouter không.
4. Model có được cấu hình không.
5. Node.js có hoạt động không.
6. npm có hoạt động không.
7. Không có lỗi trong logs.

---

# Lệnh kiểm tra nhanh tất cả trong một lần

```bash
cd ~/hermes-container-preconfig && \
docker compose ps && \
echo "=== CONTAINER LOGS ===" && \
docker logs --tail 50 hermes-test && \
echo "=== NODE / NPM ===" && \
docker exec hermes-test bash -lc '
which node || true
node --version || true
which npm || true
npm --version || true
' && \
echo "=== HERMES STATUS ===" && \
docker exec hermes-test bash -lc '
export HERMES_HOME=/data/hermes
export PATH=/data/hermes/bin:/data/hermes/node/bin:/data/hermes/hermes-agent/venv/bin:$PATH
hermes status
'
```
# Hermes Container Preconfig

Docker container chạy Hermes Agent với cấu hình OpenRouter được pre-configured.

## Features

- Ubuntu 24.04
- Hermes Agent
- OpenRouter
- Pre-configured model
- Web terminal
- Persistent `/data`
- Port `7860`
- Docker deployment
- Automatic Hermes installation

## Port

The application listens on:

`7860`

## Configuration

The OpenRouter API key is provided through the container environment/configuration.

## Local Docker

```bash
docker compose up -d
