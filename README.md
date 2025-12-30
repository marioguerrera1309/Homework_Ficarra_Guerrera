# Homework_3_DSBD_Ficarra_Guerrera
## Prerequisiti
- Docker Desktop on Windows
- kind v0.23+ and kubectl v1.30+
- secrets.yaml
## Secrets.yaml
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: smtp-secret
  namespace: homework
type: Opaque
stringData:
  SMTP_SERVER: smtp.gmail.com
  SMTP_PORT: "587"
  SENDER_EMAIL: tuaemail@gmail.com
  SENDER_PASSWORD: tuapassword
---
apiVersion: v1
kind: Secret
metadata:
  name: api-credentials
  namespace: homework
type: Opaque
stringData:
  username: tuousername
  password: tuapasswordapi
```
Per ottenere le credenziali da inserire in secrets.yaml bisogna:
1) Registrarsi al sito OpenSky Network, e ottenere,
   cliccando su “Reset Credential” nella sezione “API Client”, un json contenente il client-id
   (username) e il client secret (password).
   Per ottenere, SENDER_PASSOWRD, supponendo che si desideri inviare le mail di notifica
   attraverso GMAIL, occorre cliccare sul seguente link: https://myaccount.google.com/apppasswords?pli=1&rapt=AEjHL4OpE8c88t084a05ISyxi6hFFutuck_eyFsgeC4kUv0bLeQ8mIaVBZZOQV4E9meQQaP4QT231IRK26CJVsQXpefpYObR86RTAutrqw9zyR-Aq_sw3CA.
   Da qui, si attiva la password per applicazioni, da inserire nel campo relativo alla
   SENDER_PASSWORD.
2) inserire i certificati SSL nella directory nginx/. Per fare ciò bisogna prima creare una cartella SSL_CERTIFICATE all’interno della directory
   nginx del progetto. Successivamente, ci spostiamo sul pathname nginx/SSL_CERTIFICATE ed
   eseguiamo i seguenti comandi
```powershell
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout nginx-selfsigned.key \
    -out nginx-selfsigned.crt \
    -subj "/C=IT/ST=Italy/L=CT/O=Uni/OU=Dev/CN=localhost"
```
Dopo aver settato il file secrets.yaml, per garantire il funzionamento di NGINX, occorre cercare il path
C:\Windows\System32\drivers\etc, aprire il file hosts tramite blocco note, e inserire la riga
“127.0.0.1 apigate.com”.
## Test
Per effettuare un test del funzionamento dell’applicazione, è opportuno eseguire i sequenti comandi:
```powershell
kind create cluster --config k8s/kind-cluster.yaml --name homework
docker build -t usermanager:local .\usermanager
docker build -t datacollector:local .\datacollector
docker build -t alertsystem:local .\alertsystem
docker build -t alertnotifiersystem:local .\alertnotifiersystem
docker pull prom/prometheus:v2.45.0
docker build -t nginx-gateway:local .\nginx
kind load docker-image usermanager:local --name homework
kind load docker-image datacollector:local --name homework
kind load docker-image alertsystem:local --name homework
kind load docker-image alertnotifiersystem:local --name homework
kind load docker-image nginx-gateway:local --name homework
kind load docker-image prom/prometheus:v2.45.0 --name homework
kubectl apply -f k8s/namespace.yaml
kubectl create configmap user-db-init --from-file=init.sql=./init_user_db.sql -n homework
kubectl create configmap data-db-init --from-file=init.sql=./init_data_db.sql -n homework
docker run --rm nginx:latest cat /etc/nginx/nginx.conf > $env:TEMP\_nginx.conf
kubectl create configmap nginx-config --from-file=routing.conf=./nginx/configs/routing.conf -n homework
kubectl create secret tls tls-secret --cert=./nginx/SSL_certificate/nginx-selfsigned.crt --key=./nginx/SSL_certificate/nginx-selfsigned.key -n homework
kubectl apply -n homework -f secrets.yaml
kubectl apply -n homework -f k8s/postgres-user.yaml
kubectl apply -n homework -f k8s/postgres-data.yaml
kubectl apply -n homework -f k8s/kafka.yaml
```
Attendi che `user-db`, `data-db` e `kafka-0` siano pronti.
Per verificare lo stato dei pods: 
```powershell
kubectl get pods -n homework
```
Una volta attivi `user-db`, `data-db` e `kafka-0` eseguire:
```powershell
kubectl apply -n homework -f k8s/usermanager.yaml
kubectl apply -n homework -f k8s/datacollector.yaml
kubectl apply -n homework -f k8s/alertsystem.yaml
kubectl apply -n homework -f k8s/alertnotifiersystem.yaml
kubectl apply -n homework -f k8s/nginx.yaml
kubectl apply -n homework -f k8s/prometheus.yaml
kubectl apply -n homework -f k8s/prometheus-rbac.yaml
```