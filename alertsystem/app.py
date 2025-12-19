from confluent_kafka import Consumer, Producer, KafkaException, KafkaError
import json
import os
from collections import deque
KAFKA_BROKER_LIST = os.environ.get('KAFKA_BROKER_LIST')
consumer_config = {
    'bootstrap.servers': KAFKA_BROKER_LIST,
    'group.id': 'processor-group',
    'auto.offset.reset': 'earliest',
    'enable.auto.commit': False,
}
producer_config = {
    'bootstrap.servers': KAFKA_BROKER_LIST,
    'linger.ms': 100,
}
consumer = Consumer(consumer_config)
producer = Producer(producer_config)
topic1 = 'to-alert-system'
topic2 = 'to-notifier'
consumer.subscribe([topic1])
def delivery_report(err, msg):
    if err:
        print(f"[KAFKA PROD ERROR] Failed to produce to {topic2}: {err}")
    else:
        print(f"Stats sent to {topic2} at offset {msg.offset()}")
def process_and_produce(flight_data, msg):
    airport_code = flight_data.get('airport_code')
    total_flights = flight_data.get('total_flights')
    thresholds = flight_data.get('users_and_thresholds', [])
    if not airport_code or total_flights is None or not thresholds:
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
    while True:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                print(f"End of partition {msg.partition()}")
            else:
                print(f"Consumer error: {msg.error()}")
            continue
        try:
            flight_data = json.loads(msg.value().decode('utf-8'))
            print(f"[RECEIVED] Dati volo da DC: {flight_data['airport_code']} ({flight_data['total_flights']} voli)", file=os.sys.stderr)
            process_and_produce(flight_data, msg)
            consumer.commit(msg, asynchronous=False)
            print(f"[COMMIT SUCCESS] Messaggio {msg.offset()} elaborato e offset committato.", file=os.sys.stderr)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Malformed message: {e}")
            consumer.commit(msg, asynchronous=False)
            continue
except KeyboardInterrupt:
    print("\nConsumer-Producer interrupted by user.")
finally:
    print("Flushing producer...")
    producer.flush(timeout=10)
    print("Closing consumer...")
    consumer.close()
    print("Shutdown complete")