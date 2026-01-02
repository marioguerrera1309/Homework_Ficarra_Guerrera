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
  name: app-secrets
  namespace: homework
type: Opaque
stringData:
  USERNAME_API: "TuoUsername"
  PASSWORD_API: "TuaPassword"
  SMTP_SERVER: "smtp.gmail.com"
  SMTP_PORT: "587"
  SENDER_EMAIL: "TuaEmail"
  SENDER_PASSWORD: "TuaPassword"
---
apiVersion: v1
kind: Secret
metadata:
  name: apigw-tls
  namespace: homework
type: Opaque
data:
  nginx.selfsigned.crt: ""
  nginx.selfsigned.key: ""
```
Per ottenere le credenziali da inserire in secrets.yaml bisogna:
1) Registrarsi al sito OpenSky Network, e ottenere,
   cliccando su “Reset Credential” nella sezione “API Client”, un json contenente il client-id
   (username) e il client secret (password).
   Per ottenere, SENDER_PASSOWRD, supponendo che si desideri inviare le mail di notifica
   attraverso GMAIL, occorre cliccare sul seguente link: https://myaccount.google.com/apppasswords?pli=1&rapt=AEjHL4OpE8c88t084a05ISyxi6hFFutuck_eyFsgeC4kUv0bLeQ8mIaVBZZOQV4E9meQQaP4QT231IRK26CJVsQXpefpYObR86RTAutrqw9zyR-Aq_sw3CA.
   Da qui, si attiva la password per applicazioni, da inserire nel campo relativo alla
   SENDER_PASSWORD.
2) Creiamo i due certificati tramite i seguenti comandi:
```powershell
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout nginx-selfsigned.key \
    -out nginx-selfsigned.crt \
    -subj "/C=IT/ST=Italy/L=CT/O=Uni/OU=Dev/CN=localhost"
```
Una volta creati li convertiamo in base64 tramite i seguenti comandi:
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("percorso\al\certificato.crt"))
[Convert]::ToBase64String([IO.File]::ReadAllBytes("percorso\alla\chiave.key"))
```
E li inseriamo in secrets.yaml.

Dopo aver settato il file secrets.yaml, per garantire il funzionamento di NGINX, occorre cercare il path
C:\Windows\System32\drivers\etc, aprire il file hosts tramite blocco note, e inserire la riga
“127.0.0.1 apigate.com”.
## Test
Per effettuare un test del funzionamento dell’applicazione, è suffficiente eseguire attraverso il seguente comando il file exe.ps1
```powershell
./scripts/exe.ps1
```