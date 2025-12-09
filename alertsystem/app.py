import os
import json
import requests
import time
from threading import Thread
from confluent_kafka import Consumer, Producer, KafkaException, KafkaError
KAFKA_HOST = os.environ.get('KAFKA_HOST')
TOPIC_IN = os.environ.get('TOPIC_IN', 'to-alert-system')
TOPIC_OUT = os.environ.get('TOPIC_OUT', 'to-notifier')
DC_HOST = os.environ.get('DATA_COLLECTOR_HOST', 'datacollector:5000')
consumer_config = {
    'bootstrap.servers': KAFKA_HOST,
    'group.id': 'alert_system_group',
    'auto.offset.reset': 'latest',
    'enable.auto.commit': False,
}
producer_config = {
    'bootstrap.servers': KAFKA_HOST,
    'acks': 'all',
    'retries': 3,
}
consumer = Consumer(consumer_config)
producer = Producer(producer_config)
consumer.subscribe([TOPIC_IN])
def delivery_report(err, msg):
    if err:
        print(f"[KAFKA PROD ERROR] Failed to produce to {TOPIC_OUT}: {err}", file=os.sys.stderr)
def get_thresholds(airport_code):
    url = f"http://{DC_HOST}/thresholds/{airport_code}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json().get('thresholds', [])
    except requests.exceptions.RequestException as e:
        print(f"[ERROR DC] Impossibile contattare Data Collector: {e}", file=os.sys.stderr)
        return []
def check_and_notify(flight_data, offset_to_commit):
    """Verifica le soglie e produce un messaggio di notifica se superate."""
    airport_code = flight_data.get('airport_code')
    total_flights = flight_data.get('total_flights')
    if not airport_code or total_flights is None:
        return
    thresholds = get_thresholds(airport_code)
    for th in thresholds:
        email = th['email']
        high = th['high_value']
        low = th['low_value']
        condition = None
        threshold_met = None
        if high is not None and total_flights > high:
            condition = "SUPERATA_ALTA"
            threshold_met = high
        elif low is not None and total_flights < low:
            condition = "SUPERATA_BASSA"
            threshold_met = low
        if condition:
            payload = {
                "email": email,
                "airport_code": airport_code,
                "condition_met": condition,
                "threshold_value": threshold_met
            }
            producer.produce(
                TOPIC_OUT,
                json.dumps(payload).encode('utf-8'),
                callback=delivery_report
            )
            print(f"[ALERT PRODUCER] Notifica inviata per {email}: soglia {condition} su {airport_code}", file=os.sys.stderr)
    consumer.commit(offset_to_commit, asynchronous=False)
    producer.poll(0) # Trigger callbacks
    print(f"[ALERT COMMITTED] Offset {offset_to_commit.offset()} per {airport_code}", file=os.sys.stderr)
def start_alert_system():
    print(f"[ALERT SYSTEM] Avvio consumer su topic {TOPIC_IN} con broker {KAFKA_HOST}...")
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    print(f"[KAFKA CONSUMER ERROR] Errore consumer: {msg.error()}", file=os.sys.stderr)
                    continue
            try:
                flight_data = json.loads(msg.value().decode('utf-8'))
                print(f"[RECEIVED] Dati volo da DC: {flight_data['airport_code']} ({flight_data['total_flights']} voli)", file=os.sys.stderr)
                check_and_notify(flight_data, msg)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[ERROR PARSING] Messaggio malformato: {e}", file=os.sys.stderr)
                consumer.commit(msg) #committ del messaggio per evitare un deadlock
                continue
    except KeyboardInterrupt:
        print("\nAlertSystem interrotto dall'utente.", file=os.sys.stderr)
    finally:
        print("Flushing producer...", file=os.sys.stderr)
        producer.flush(timeout=10)
        print("Closing consumer...", file=os.sys.stderr)
        consumer.close()
if __name__ == '__main__':
    time.sleep(10)
    start_alert_system()