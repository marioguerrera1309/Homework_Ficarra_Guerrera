Homework_3_DSBD_Ficarra_Guerrera

Per effettuare un test del funzionamento dell’applicazione, è opportuno creare, all’interno
della repository principale, un file .env in cui inserire le credenziali:

username=fornito in seguito alla registrazione ad OpenSky

password=fornita in seguito alla registrazione ad OpenSky


SMTP_SERVER=servizio con il quale si intende inviare la mail (es: smtp.gmail.com)


SMTP_PORT=587 (standard per SMTP)


SENDER_EMAIL= email con la quale si intende inviare le email di notifica


SENDER_PASSWORD= password fornita in seguito ad attivazione della password per applicazioni


Per ottenere username e password, occorre registrarsi al sito OpenSky Network, e ottenere,
cliccando su “Reset Credential” nella sezione “API Client” un json contenente il client-id
(username) e il client secret (password). 

Per ottenere, SENDER_PASSOWRD, supponendo che si desideri inviare le mail di notifica
attraverso GMAIL, occorre cliccare sul seguente link: https://myaccount.google.com/apppasswords?pli=1&rapt=AEjHL4OpE8c88t084a05ISyxi6hFFutuck_eyFsgeC4kUv0bLeQ8mIaVBZZOQV4E9meQQaP4QT231IRK26CJVsQXpefpYObR86RTAutrqw9zyR-Aq_sw3CA


Da qui, si attiva la password per applicazioni, da inserire nel campo relativo alla
SENDER_PASSWORD.


Dopo aver settato il file .env, per garantire il funzionamento di NGINX, occorre cercare il path
C:\Windows\System32\drivers\etc, aprire il file hosts tramite blocco note, e inserire la riga
“127.0.0.1 apigate.com”. 

Una volta assegnato al DNS locale, tramite il file hosts, il dominio apigate.com con l’indirizzo
di localhost (127.0.0.1), dobbiamo inserire i certificati SSL nella directory nginx/ .


Per fare ciò bisogna prima creare una cartella SSL_CERTIFICATE all’interno della directory
nginx del progetto. Successivamente, ci spostiamo sul pathname nginx/SSL_CERTIFICATE ed
eseguiamo i seguenti comandi


    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout nginx-selfsigned.key \
        -out nginx-selfsigned.crt \
        -subj "/C=IT/ST=Italy/L=CT/O=Uni/OU=Dev/CN=localhost"
