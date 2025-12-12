import os
import smtplib
from email.message import EmailMessage
from confluent_kafka import Consumer, KafkaException
import json
from smtplib import SMTPRecipientsRefused, SMTPServerDisconnected, SMTPAuthenticationError

# --- CONFIGURAZIONE KAFKA (COME FATTO IN PRECEDENZA) ---
KAFKA_BROKER_LIST = os.environ.get('KAFKA_BROKER_LIST')
CONSUMER_GROUP = os.environ.get('CONSUMER_GROUP_ID', 'final-consumer-group')
TOPIC_INPUT_NAME = os.environ.get('TOPIC_INPUT_NAME', 'to-notifier')


consumer_config = {
    'bootstrap.servers': KAFKA_BROKER_LIST,
    'group.id': CONSUMER_GROUP,
    'auto.offset.reset': 'earliest',
    'enable.auto.commit': False,
    'max.poll.interval.ms': 300000,
}

consumer = Consumer(consumer_config)
consumer.subscribe([TOPIC_INPUT_NAME])

# --- NUOVA CONFIGURAZIONE SMTP ---
SMTP_SERVER = os.environ.get('SMTP_SERVER')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')


def format_email_body(email, airport, condition, threshold):
    # ... (La tua funzione format_email_body rimane invariata)
    if condition == "SUPERATA_SOGLIA_ALTA":
        type_str = "superiore"
        verb = "ha superato"
    elif condition == "SUPERATA_SOGLIA_BASSA":
        type_str = "inferiore"
        verb = "è sceso sotto"
    else:
        type_str = "sconosciuta"
        verb = "ha raggiunto una condizione anomala"

    subject = f"Allerta Voli: Soglia {type_str} su {airport}"
    body = (
        f"Ciao {email},\n\n"
        f"Ti informiamo che il numero di voli totali per l'aeroporto {airport} "
        f"{verb} la soglia limite di {threshold}.\n\n"
        f"Condizione rilevata: {condition}.\n"
    )
    return subject, body

def send_notification(recipient_email, airport, condition, threshold):
    """
    Tenta l'invio dell'email via SMTP con gestione degli errori.
    Ritorna True se l'invio ha successo (o se l'errore è permanente e decidiamo di committare).
    Ritorna False se l'errore è temporaneo (e deve essere rielaborato).
    """
    subject, body = format_email_body(recipient_email, airport, condition, threshold)

    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient_email

    try:
        # Connessione al server SMTP
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() # Necessario per la sicurezza (es. Gmail)
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)

        print(f"[EMAIL SUCCESS] Notifica inviata a {recipient_email}.", file=os.sys.stderr)
        return True # Invio riuscito

    except SMTPRecipientsRefused as e:
        # Gestione casella inesistente/rifiutata (Errore 550 o simile)
        print(f"[EMAIL FAILED PERMANENT] Destinatario {recipient_email} rifiutato o inesistente: {e}", file=os.sys.stderr)
        # Se la casella non esiste, è un errore permanente. Non possiamo fare altro che committare l'offset
        # per non bloccare il consumer su questo messaggio.
        return True

    except SMTPAuthenticationError as e:
        # Errore di login (Password sbagliata, app password necessaria, ecc.)
        print(f"[EMAIL ERROR CRITICAL] Autenticazione SMTP fallita: {e}", file=os.sys.stderr)
        # Questo è un errore che richiede un intervento manuale. Non committare l'offset per riprovare (o bloccare).
        raise e # Rilancia l'errore per uscire dal loop e riprovare (o fallire)

    except (SMTPServerDisconnected, TimeoutError) as e:
        # Errore temporaneo (Timeout, server disconnesso)
        print(f"[EMAIL FAILED TEMPORARY] Errore di rete o timeout: {e}", file=os.sys.stderr)
        # È un errore temporaneo: Ritorna False per NON committare l'offset.
        return False

    except Exception as e:
        print(f"[EMAIL FAILED UNKNOWN] Errore sconosciuto durante l'invio a {recipient_email}: {e}", file=os.sys.stderr)
        return True # Trattiamo come permanente per non bloccare, ma si può scegliere False

# --- CICLO DI ELABORAZIONE KAFKA ---

try:
    print(f"AlertNotifierSystem started. Waiting for messages on {TOPIC_INPUT_NAME}...")

    # ...
    # (Il loop while True con poll e gestione errori Kafka rimane invariato)

    while True:
        msg = consumer.poll(1.0)

        if msg is None: continue
        if msg.error(): # ... (gestione errori Kafka)
            # ...
            continue

        try:
            alert_data = json.loads(msg.value().decode('utf-8'))

            email = alert_data['email']
            airport = alert_data['airport_code']
            condition = alert_data['condition_met']
            threshold = alert_data['threshold_value']

            # Esegue l'azione esterna
            if send_notification(email, airport, condition, threshold):
                # Se la notifica è riuscita O l'errore è permanente (casella inesistente),
                # committiamo l'offset per evitare di rielaborare.
                consumer.commit(msg, asynchronous=False)
                print(f"[COMMIT SUCCESS] Notifica per {email} gestita e offset {msg.offset()} committato.")
            else:
                # Se l'errore è temporaneo (es. timeout), NON committiamo l'offset.
                # Il consumer tenterà di rielaborare questo messaggio al prossimo riavvio.
                print(f"[RETRY NEEDED] Notifica non inviata, non committiamo. Riproveremo.")

        except (json.JSONDecodeError, KeyError) as e:
            # Gestione messaggi malformati
            print(f"[PARSING ERROR] Messaggio malformato (offset {msg.offset()}): {e}", file=os.sys.stderr)
            consumer.commit(msg) # Commit malformato per non bloccare
            continue

except KeyboardInterrupt:
    print("\nConsumer interrupted by user.")

# ... (blocco finally)
finally:
    print("Closing consumer...")
    consumer.close()
    print("Shutdown complete")