# Deploy on kind (Kubernetes in Docker)

This guide deploys the project to a local Kubernetes cluster using kind.

## Prerequisites
- Docker Desktop on Windows
- kind v0.23+ and kubectl v1.30+
- Project images buildable locally

## 0) Install kind
choco install kind
## 1) Create the kind cluster
```powershell
kind create cluster --config k8s/kind-cluster.yaml --name homework
kubectl cluster-info
```
If port 443 is busy, change `hostPort` in `k8s/kind-cluster.yaml` to another port (e.g., 8443) and re-create the cluster.

## 2) Build local Docker images
Run from the project root:
```powershell
# Build service images
docker build -t usermanager:local .\usermanager
docker build -t datacollector:local .\datacollector
docker build -t alertsystem:local .\alertsystem
docker build -t alertnotifiersystem:local .\alertnotifiersystem


# Build the nginx gateway image
docker build -t nginx-gateway:local .\nginx
```

## 3) Load images into the kind cluster
```powershell
kind load docker-image usermanager:local --name homework
kind load docker-image datacollector:local --name homework
kind load docker-image alertsystem:local --name homework
kind load docker-image alertnotifiersystem:local --name homework
kind load docker-image nginx-gateway:local --name homework
```

## 4) Create namespace and config prerequisites
```powershell
# Namespace
kubectl apply -f k8s/namespace.yaml

# Postgres init SQL (uses your existing SQL files)
kubectl create configmap user-db-init --from-file=init.sql=./init_user_db.sql -n homework
kubectl create configmap data-db-init --from-file=init.sql=./init_data_db.sql -n homework

# Nginx routing.conf
docker run --rm nginx:latest cat /etc/nginx/nginx.conf > $env:TEMP\_nginx.conf  # optional inspection
kubectl create configmap nginx-config --from-file=routing.conf=./nginx/configs/routing.conf -n homework

# TLS secret from your self-signed certs
kubectl create secret tls tls-secret \ 
  --cert=./nginx/SSL_certificate/nginx-selfsigned.crt \ 
  --key=./nginx/SSL_certificate/nginx-selfsigned.key \ 
  -n homework

# SMTP credentials for alert notifier (EDIT values)
kubectl create secret generic smtp-secret --from-literal=SMTP_SERVER=smtp.example.com --from-literal=SMTP_PORT=587 --from-literal=SENDER_EMAIL=user@example.com --from-literal=SENDER_PASSWORD=your_app_password -n homework

# API credentials used by datacollector (EDIT values)
kubectl create secret generic api-credentials --from-literal=username=myuser --from-literal=password=mypass -n homework
```

## 5) Deploy infrastructure (DB + Kafka)
```powershell
kubectl apply -n homework -f k8s/postgres-user.yaml
kubectl apply -n homework -f k8s/postgres-data.yaml
kubectl apply -n homework -f k8s/kafka.yaml
kubectl get pods -n homework
```
Wait until `user-db`, `data-db` and `kafka-0` are Ready.

## 6) Deploy services
```powershell
kubectl apply -n homework -f k8s/usermanager.yaml
kubectl apply -n homework -f k8s/datacollector.yaml
kubectl apply -n homework -f k8s/alertsystem.yaml
kubectl apply -n homework -f k8s/alertnotifiersystem.yaml
kubectl apply -n homework -f k8s/nginx.yaml
kubectl get pods -n homework
```

## 7) Test access
- HTTPS is exposed via kind port mapping:
  - If `hostPort: 443` was used: open `https://localhost/`
  - If you changed to 8443: open `https://localhost:8443/`
- Accept the self-signed certificate warning.

## Useful checks
```powershell
kubectl logs deploy/user-manager -n homework --tail=100
kubectl logs deploy/datacollector -n homework --tail=100
kubectl logs statefulset/kafka -n homework --tail=100
kubectl get svc -n homework
kubectl describe svc apigateway -n homework
```

## Notes
- Storage uses `emptyDir` volumes for simplicity; data is ephemeral.
- Kafka uses single-node KRaft; advertised listener is `kafka:9092` for in-cluster clients.
- Environment values mirror your docker-compose settings; update secrets where noted.
- If nginx routes reference service names, ensure they match: `user-manager`, `datacollector`.
