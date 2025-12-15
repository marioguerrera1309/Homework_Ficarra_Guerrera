import os
import smtplib
from email.message import EmailMessage
from confluent_kafka import Consumer, KafkaException
import json
from smtplib import SMTPRecipientsRefused, SMTPServerDisconnected, SMTPAuthenticationError
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
SMTP_SERVER = os.environ.get('SMTP_SERVER')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')
def format_email_body(email, airport, condition, threshold):
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
    subject, body = format_email_body(recipient_email, airport, condition, threshold)
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient_email
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        print(f"[EMAIL SUCCESS] Notifica inviata a {recipient_email}.", file=os.sys.stderr)
        return True
    except SMTPRecipientsRefused as e:
        print(f"[EMAIL FAILED PERMANENT] Destinatario {recipient_email} rifiutato o inesistente: {e}", file=os.sys.stderr)
        return True
    except SMTPAuthenticationError as e:
        print(f"[EMAIL ERROR CRITICAL] Autenticazione SMTP fallita: {e}", file=os.sys.stderr)
        raise e
    except (SMTPServerDisconnected, TimeoutError) as e:
        print(f"[EMAIL FAILED TEMPORARY] Errore di rete o timeout: {e}", file=os.sys.stderr)
        return False
    except Exception as e:
        print(f"[EMAIL FAILED UNKNOWN] Errore sconosciuto durante l'invio a {recipient_email}: {e}", file=os.sys.stderr)
        return True
try:
    print(f"AlertNotifierSystem started. Waiting for messages on {TOPIC_INPUT_NAME}...")
    while True:
        msg = consumer.poll(1.0)
        if msg is None: continue
        if msg.error():
            continue
        try:
            alert_data = json.loads(msg.value().decode('utf-8'))
            email = alert_data['email']
            airport = alert_data['airport_code']
            condition = alert_data['condition_met']
            threshold = alert_data['threshold_value']
            if send_notification(email, airport, condition, threshold):
                consumer.commit(msg, asynchronous=False)
                print(f"[COMMIT SUCCESS] Notifica per {email} gestita e offset {msg.offset()} committato.")
            else:
                print(f"[RETRY NEEDED] Notifica non inviata, non committiamo. Riproveremo.")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[PARSING ERROR] Messaggio malformato (offset {msg.offset()}): {e}", file=os.sys.stderr)
            consumer.commit(msg, asynchronous=False)
            continue
except KeyboardInterrupt:
    print("\nConsumer interrupted by user.")
finally:
    print("Closing consumer...")
    consumer.close()
    print("Shutdown complete")