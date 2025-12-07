from confluent_kafka import Consumer, KafkaException
import os
import json
import time

KAFKA_HOST = os.environ.get('KAFKA_HOST')
TOPIC_IN = os.environ.get('TOPIC_IN', 'to-notifier')

# Configurazione Consumer (AlertNotifierSystem)
consumer_config = {
    'bootstrap.servers': KAFKA_HOST,
    'group.id': 'notifier_system_group', # Group ID diverso per permettere l'indipendenza
    'auto.offset.reset': 'latest',
    'enable.auto.commit': False,
}

consumer = Consumer(consumer_config)
consumer.subscribe([TOPIC_IN])


# ==============================
# FUNZIONI DI UTILITY
# ==============================

def format_email_body(email, airport, condition, threshold):
    """Formatta il corpo dell'email in base alla condizione superata."""
    if condition == "SUPERATA_ALTA":
        type_str = "superiore"
        verb = "ha superato"
    else:
        type_str = "inferiore"
        verb = "è sceso sotto"

    subject = f"Allerta Voli: Soglia {type_str} su {airport}"
    body = (
        f"Ciao {email},\n\n"
        f"Ti informiamo che il numero di voli totali per l'aeroporto {airport} "
        f"{verb} la soglia limite di {threshold}.\n\n"
        f"Condizione rilevata: {condition}.\n"
    )
    return subject, body


# ==============================
# MAIN CONSUMER LOOP
# ==============================

def start_notifier_consumer():
    print(f"[NOTIFIER SYSTEM] Avvio consumer su topic {TOPIC_IN}...")

    try:
        while True:
            msg = consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaException._PARTITION_EOF:
                    continue
                else:
                    print(f"[KAFKA CONSUMER ERROR] Errore consumer: {msg.error()}", file=os.sys.stderr)
                    continue

            try:
                alert_data = json.loads(msg.value().decode('utf-8'))
                email = alert_data['email']
                airport = alert_data['airport_code']
                condition = alert_data['condition_met']
                threshold = alert_data['threshold_value']

                subject, body = format_email_body(email, airport, condition, threshold)

                # Simulazione invio email
                print("\n" + "="*40, file=os.sys.stderr)
                print(f"EMAIL TO: {email}", file=os.sys.stderr)
                print(f"SUBJECT: {subject}", file=os.sys.stderr)
                print(f"BODY:\n{body}", file=os.sys.stderr)
                print("="*40 + "\n", file=os.sys.stderr)

                # Commit offset dopo la corretta notifica/simulazione
                consumer.commit(msg, asynchronous=False)

            except (json.JSONDecodeError, KeyError) as e:
                print(f"[ERROR PARSING] Messaggio malformato: {e}", file=os.sys.stderr)
                consumer.commit(msg)
                continue

    except KeyboardInterrupt:
        print("\nNotifierSystem interrotto dall'utente.", file=os.sys.stderr)
    finally:
        print("Closing consumer...", file=os.sys.stderr)
        consumer.close()

if __name__ == '__main__':
    time.sleep(15)
    start_notifier_consumer()