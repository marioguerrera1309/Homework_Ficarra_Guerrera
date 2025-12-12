from confluent_kafka import Consumer, Producer, KafkaException
import json
import os
from datetime import datetime
from collections import deque

KAFKA_BROKER_LIST = os.environ.get('KAFKA_BROKER_LIST')
# Consumer configuration
consumer_config = {
    'bootstrap.servers': KAFKA_BROKER_LIST,
    'group.id': 'processor-group',
    'auto.offset.reset': 'earliest',
    'enable.auto.commit': False,  # Manual commit for better control
}

# Producer configuration
producer_config = {
    'bootstrap.servers': KAFKA_BROKER_LIST,
    'linger.ms': 100,  # Batching for efficiency
}

consumer = Consumer(consumer_config)
producer = Producer(producer_config)

topic1 = 'to-alert-system'  # Source topic for input messages
topic2 = 'to-notifier'  # Destination topic for output statistics

# Use deque with maxlen for sliding window (prevents memory leak)
WINDOW_SIZE = 100  # Keep only last 100 values
values = deque(maxlen=WINDOW_SIZE)

consumer.subscribe([topic1])

def delivery_report(err, msg):
    """Callback to verify production to TOPIC2"""
    if err:
        print(f"[KAFKA PROD ERROR] Failed to produce to {topic2}: {err}")
    else:
        print(f"Stats sent to {topic2} at offset {msg.offset()}")

def process_and_produce(flight_data):
    airport_code = flight_data.get('airport_code')
    total_flights = flight_data.get('total_flights')
    thresholds = flight_data.get('users_and_thresholds', []) # Prendi il nuovo campo

    if not airport_code or total_flights is None or not thresholds:
        # Commit e salta se mancano dati o non ci sono utenti da avvisare
        consumer.commit(msg, asynchronous=False)
        return

    print(f"Check and notify con {len(thresholds)} profili", file=os.sys.stderr)

    for th in thresholds:
        email = th['email']
        high = th['high_value']
        low = th['low_value']
        condition = None
        threshold_met = None
        if high is not None and total_flights > high:
            condition = "SUPERATA_SOGLIA_ALTA"
            threshold_met = high
        elif low is not None and total_flights < low:
            condition = "SUPERATA_SOGLIA_BASSA"
            threshold_met = low
        if condition:
            payload = {
                "email": email,
                "airport_code": airport_code,
                "condition_met": condition,
                "threshold_value": threshold_met
            }
            producer.produce(
                topic2,
                json.dumps(payload).encode('utf-8'),
                callback=delivery_report
            )
            print(f"[ALERT PRODUCER] Notifica inviata per {email}: soglia {condition} su {airport_code}", file=os.sys.stderr)

    producer.poll(0)

try:
    print(f"Consumer-Producer started. Window size: {WINDOW_SIZE}")
    message_count = 0

    while True:
        # Poll with timeout
        msg = consumer.poll(1.0)

        if msg is None:
            continue

        if msg.error():
            # Specific error handling
            if msg.error().code() == KafkaException._PARTITION_EOF:
                print(f"End of partition {msg.partition()}")
            else:
                print(f"Consumer error: {msg.error()}")
            continue

        # Parse message
        try:
            flight_data = json.loads(msg.value().decode('utf-8'))
            print(f"[RECEIVED] Dati volo da DC: {flight_data['airport_code']} ({flight_data['total_flights']} voli)", file=os.sys.stderr)
            process_and_produce(flight_data)
            message_count += 1
        except (json.JSONDecodeError, KeyError) as e:

            print(f"[ERROR PARSING] Messaggio malformato: {e}", file=os.sys.stderr)

            # Improvement: Commit every N messages instead of always
            if message_count % 10 == 0:
                consumer.commit(asynchronous=False)
                print(f"Committed offset {msg.offset()}")

        except (json.JSONDecodeError, KeyError) as e:
            print(f"Malformed message: {e}")
            # Commit malformed messages to avoid reprocessing
            consumer.commit(msg)
            continue

except KeyboardInterrupt:
    print("\nConsumer-Producer interrupted by user.")
finally:
    # Final cleanup
    print("Flushing producer...")
    producer.flush(timeout=10)
    print("Closing consumer...")
    consumer.close()
    print("Shutdown complete")


