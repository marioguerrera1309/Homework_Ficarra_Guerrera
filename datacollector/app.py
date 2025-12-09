import sys
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import os
import requests
import json
import calendar
import service_pb2
import service_pb2_grpc
import grpc
import time
import schedule
import threading
from datetime import datetime, timedelta
from sqlalchemy import select, func, cast, BigInteger
from sqlalchemy.sql.expression import text
from circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from confluent_kafka import Producer
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
API_BASE_URL = "https://opensky-network.org/api"
opensky_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=requests.exceptions.RequestException
)
KAFKA_HOST = os.environ.get('KAFKA_HOST')
KAFKA_TOPIC_ALERT = os.environ.get('KAFKA_TOPIC_ALERT', 'to-alert-system')
producer_config = {
    'bootstrap.servers': KAFKA_HOST, # KAFKA_HOST è già definito come kafka:9092
    'acks': 'all',
    'retries': 3,
}
producer = Producer(producer_config)
class Flight(db.Model):
    __tablename__ = 'flights'
    icao24 = db.Column(db.String(50), primary_key=True) #idvolo
    callsign = db.Column(db.String(50), nullable=True)
    est_departure_airport = db.Column(db.String(10), nullable=True) #aereoportopartenza
    est_arrival_airport = db.Column(db.String(10), nullable=True) #aereoportoarrivo
    first_seen_utc = db.Column(db.String(30), nullable=True)
    last_seen_utc = db.Column(db.String(30), nullable=True)
    ingestion_time = db.Column(db.DateTime, default=datetime.utcnow)
class Interest(db.Model):
    __tablename__ = 'interests'
    email = db.Column(db.String(255), primary_key=True)
    airport_code = db.Column(db.String(10), primary_key=True)
    high_value = db.Column(db.Integer, nullable=True)
    low_value = db.Column(db.Integer, nullable=True)
class User(db.Model):
    __tablename__ = 'users'
    email = db.Column(db.String(255), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    surname = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
API_BASE_URL = "https://opensky-network.org/api"
TOKEN=None
SERVER_ADDRESS='usermanager:'+os.environ.get('GRPC_PORT')
def CheckUserStatus(email):
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub=service_pb2_grpc.UserManagerServiceStub(channel)
        print(f"Client: invio la richiesta con email: {email}", file=os.sys.stderr)
        response=stub.CheckUserStatus(service_pb2.UserVerification(email=email))
        status=response.status
        print(f"Ricevuta risposta: {status}", file=os.sys.stderr)
        return status
def get_access_token_logic():
    data = {
        "grant_type": "client_credentials",
        "client_id": os.environ.get('USERNAME_API'),
        "client_secret": os.environ.get('PASSWORD_API')
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    try:
        response = requests.post(TOKEN_URL, data=data, headers=headers)
        response.raise_for_status()
        token_info=response.json()
        access_token = token_info.get('access_token')
        if access_token:
            print(f"Token di accesso ottenuto con successo.",  file=os.sys.stderr)
            return access_token
        else:
            print(f"Errore: 'access_token' non trovato nella risposta. Risposta completa: {token_info}",  file=os.sys.stderr)
            return None
    except requests.exceptions.RequestException as e:
        print(f"Errore nella richiesta del token: {e}")
        raise e
def get_access_token():
    try:
        return opensky_breaker.call(get_access_token_logic)
    except CircuitBreakerOpenException:
        print("Circuit Breaker è aperto. Non posso richiedere il token.", file=os.sys.stderr)
        return None
    except Exception as e:
        raise e
def delivery_report(err, msg):
    if err:
        print(f"[KAFKA DELIVERY ERROR] Delivery failed: {err}", file=os.sys.stderr)
def publish_flight_count(airport_code, total_flights):
    payload = {
        "airport_code": airport_code,
        "total_flights": total_flights,
        "timestamp": datetime.utcnow().isoformat()
    }
    try:
        producer.produce(
            KAFKA_TOPIC_ALERT,
            json.dumps(payload).encode('utf-8'),
            callback=delivery_report
        )
        producer.poll(0)
        print(f"[KAFKA PRODUCER] Inviati dati su {airport_code} a {KAFKA_TOPIC_ALERT}.", file=os.sys.stderr)
    except Exception as e:
        print(f"[KAFKA ERROR] Errore invio Kafka per {airport_code}: {e}", file=os.sys.stderr)
@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Data Collector is running"}), 200
@app.route('/flights', methods=['POST'])
def flights():
    data = request.get_json()
    email=data.get("email")
    if email is None:
        return jsonify({"message": "Paramentro email mancante"}), 200
    else:
        x=CheckUserStatus(email)
        if x == service_pb2.UserStatus.ACTIVE:
            int = db.session.scalars(
                select(Flight)
                .join(Interest, Flight.est_departure_airport == Interest.airport_code)
                .where(Interest.email == email)
            ).all()
            int_list = [{"icao24": i.icao24, "callsign": i.callsign, "est_departure_airport": i.est_departure_airport, "est_arrival_airport": i.est_arrival_airport, "first_seen_utc": i.first_seen_utc, "last_seen_utc": i.last_seen_utc, "ingestion_time": i.ingestion_time} for i in int]
            return jsonify({"Flights": int_list}), 200
        else:
            print(f"L'utente non esiste", file=os.sys.stderr)
            return jsonify({"message": "L'utente non esiste"}), 200
@app.route('/add_interest', methods=['POST'])
def add_interest():
    data = request.get_json()
    email=data.get("email")
    airport=data.get("airport", [])
    if email is None or airport is None:
        return jsonify({"message": "Paramentri email, aereporti mancanti"}), 200
    else:
        x=CheckUserStatus(email)
        if x == service_pb2.UserStatus.ACTIVE:
        #print(f"x: {x}", file=os.sys.stderr)
            for interest_data in airport:
                high_value = interest_data.get("high_value")
                low_value = interest_data.get("low_value")
                airport_code = interest_data.get("airport_code")
                if high_value is not None:
                    high_value = int(high_value)
                if low_value is not None:
                    low_value = int(low_value)
                if not airport_code:
                    return jsonify({"error": "Campo 'airport_code' mancante in un elemento"}), 400
                if high_value is not None and low_value is not None and high_value <= low_value:
                    return jsonify({"error": f"Per l'aeroporto {airport_code}, high-value deve essere maggiore di low-value."}), 400
                new_interest = Interest(
                    email=email,
                    airport_code=airport_code,
                    high_value=high_value,
                    low_value=low_value
                )
                db.session.merge(new_interest)
            db.session.commit()
            return jsonify({"message": f"Utente {email} verificato e {len(airport)} interessi aggiunti."}), 200
        else:
            print(f"L'utente non esiste", file=os.sys.stderr)
            return jsonify({"message": "L'utente non esiste"}), 200
@app.route('/interest', methods=['POST'])
def interest():
    data = request.get_json()
    email=data.get("email")
    if email is None:
        return jsonify({"message": "Paramentro email mancante"}), 200
    else:
        x=CheckUserStatus(email)
        if x == service_pb2.UserStatus.ACTIVE:
            int= db.session.scalars(db.select(Interest).where(Interest.email == email)).all()
            int_list = [{"email": i.email, "airport_code": i.airport_code} for i in int]
            return jsonify({"Interest": int_list}), 200
        else:
            print(f"L'utente non esiste o è stato eliminato", file=os.sys.stderr)
            return jsonify({"message": "L'utente non esiste o è stato eliminato"}), 200
@app.route("/last_flight/<airport_code>", methods=["GET"])
def get_last_flight(airport_code):
    with app.app_context():
        try:
            last_flight = Flight.query.filter_by(est_departure_airport=airport_code) \
                .order_by(Flight.first_seen_utc.desc()) \
                .first()
            if not last_flight:
                return jsonify({"message": f"Nessun dato di volo trovato per l'aeroporto {airport_code}."}), 404
            last_flight_a = Flight.query.filter_by(est_arrival_airport=airport_code) \
                .order_by(Flight.first_seen_utc.desc()) \
                .first()
            if not last_flight_a:
                return jsonify({"message": f"Nessun dato di volo trovato per l'aeroporto {airport_code}."}), 404
            flight_data = {
                "icao24_departure": last_flight.icao24,
                "callsign_departure": last_flight.callsign,
                "est_departure_airport_departure": last_flight.est_departure_airport,
                "est_arrival_airport_departure": last_flight.est_arrival_airport,
                "first_seen_utc_departure": last_flight.first_seen_utc,
                "last_seen_utc_departure": last_flight.last_seen_utc,
                "icao24_arrival": last_flight_a.icao24,
                "callsign_arrival": last_flight_a.callsign,
                "est_departure_airport_arrival": last_flight_a.est_departure_airport,
                "est_arrival_airport_arrival": last_flight_a.est_arrival_airport,
                "first_seen_utc_arrival": last_flight_a.first_seen_utc,
                "last_seen_utc_arrival": last_flight_a.last_seen_utc,
            }
            return jsonify(flight_data), 200
        except Exception as e:
            app.logger.error(f"Errore nel recupero dell'ultimo volo: {e}")
            return jsonify({"error": "Errore interno durante la query"}), 500

@app.route("/average_flights/<airport_code>", methods=["GET"])
def calculate_average_flights(airport_code):
    days = request.args.get('days', 7, type=int) #default=7
    if days <= 0:
        return jsonify({"error": "Il numero di giorni (X) deve essere maggiore di zero."}), 400
    NOW_UTC = datetime.utcnow()
    BEGIN_DATETIME = NOW_UTC - timedelta(days=days)
    END_DATETIME = NOW_UTC
    with app.app_context():
        try:
            total_flights = db.session.query(func.count(Flight.est_departure_airport)) \
                .filter(Flight.est_departure_airport == airport_code) \
                .filter(Flight.first_seen_utc.cast(db.DateTime) >= BEGIN_DATETIME) \
                .filter(Flight.last_seen_utc.cast(db.DateTime) <= END_DATETIME) \
                .scalar()
            total_flights = total_flights if total_flights is not None else 0
            average = total_flights / days if days > 0 else 0
            return jsonify({
                "aeroporto_icao": airport_code,
                "periodo_giorni": days,
                "voli_totali": total_flights,
                "media_giornaliera": round(average, 2)
            }), 200
        except Exception as e:
            app.logger.error(f"Errore nel calcolo della media: {e}")
            return jsonify({"error": "Errore interno durante il calcolo della media"}), 500
@app.route('/flights_by_period', methods=['GET'])
def get_flights_by_period():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    if not start_date_str or not end_date_str:
        return jsonify({"error": "I parametri 'start_date' (YYYY-MM-DD) e 'end_date' sono obbligatori."}), 400
    try:
        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
    except ValueError:
        return jsonify({"error": "Formato data non valido. Usa YYYY-MM-DD."}), 400
    with app.app_context():
        try:
            results = db.session.execute(
                select(
                    Flight.est_departure_airport.label('airport'),
                    func.count(Flight.icao24).label('total_flights')
                )
                .filter(Flight.est_departure_airport.isnot(None))
                .filter(Flight.first_seen_utc.cast(db.DateTime) >= start_dt)
                .filter(Flight.first_seen_utc.cast(db.DateTime) < end_dt)
                .group_by(Flight.est_departure_airport)
            ).all()
            if not results:
                return jsonify({"message": "Nessun volo trovato nell'intervallo specificato."}), 200
            output_list = [
                {"aeroporto": r.airport, "voli_totali": r.total_flights}
                for r in results
            ]
            return jsonify({
                "periodo_richiesto": f"Da {start_date_str} a {end_date_str}",
                "voli_per_aeroporto": output_list
            }), 200
        except Exception as e:
            app.logger.error(f"Errore query DB: {e}")
            return jsonify({"error": "Errore interno durante l'aggregazione"}), 500
@app.route('/flight_duration/<airport_code>', methods=['GET'])
def get_flight_duration(airport_code):
    with app.app_context():
        flights = db.session.scalars(
            select(Flight)
            .filter(
                (Flight.est_departure_airport == airport_code) |
                (Flight.est_arrival_airport == airport_code)
            )
        ).all()
        if not flights:
            return jsonify({"message": f"Nessun volo trovato da/per {airport_code}."}), 404
        min_duration = timedelta(days=9999)
        max_duration = timedelta(seconds=0)
        longest_flight = None
        shortest_flight = None
        for flight in flights:
            try:
                start = datetime.strptime(flight.first_seen_utc, '%Y-%m-%d %H:%M:%S')
                end = datetime.strptime(flight.last_seen_utc, '%Y-%m-%d %H:%M:%S')
                duration = end - start
                if duration > max_duration:
                    max_duration = duration
                    longest_flight = flight
                if duration < min_duration and duration.total_seconds() > 0:
                    min_duration = duration
                    shortest_flight = flight
            except (ValueError, TypeError):
                continue
        if not longest_flight:
            return jsonify({"message": f"Dati temporali non sufficienti per calcolare la durata dei voli in {airport_code}."}), 404
        return jsonify({
            "aeroporto_analizzato": airport_code,
            "volo_piu_lungo": {
                "icao24": longest_flight.icao24,
                "callsign": longest_flight.callsign,
                "durata_secondi": int(max_duration.total_seconds()),
                "durata_formattata": str(max_duration)
            },
            "volo_piu_breve": {
                "icao24": shortest_flight.icao24,
                "callsign": shortest_flight.callsign,
                "durata_secondi": int(min_duration.total_seconds()),
                "durata_formattata": str(min_duration)
            }
        }), 200
@app.route('/thresholds/<airport_code>', methods=['GET'])
def get_thresholds_by_airport(airport_code):
    with app.app_context():
        thresholds = db.session.execute(
            select(Interest.email, Interest.high_value, Interest.low_value)
            .where(Interest.airport_code == airport_code)
            .filter((Interest.high_value.isnot(None)) | (Interest.low_value.isnot(None)))
        ).all()
        thresholds_list = [
            {"email": t[0], "high_value": t[1], "low_value": t[2]}
            for t in thresholds
        ]
        return jsonify({"thresholds": thresholds_list}), 200
def verify_users():
    users = db.session.query(Interest.email).distinct().all()
    users_removed = 0
    #print(f"Verifica", file=os.sys.stderr)
    for (email,) in users:
        x=CheckUserStatus(email)
        if x != service_pb2.UserStatus.ACTIVE:
            print(f"Utente {email} non più attivo (Status: {x}). Rimozione interessi...", file=os.sys.stderr)
            db.session.query(Interest).filter(Interest.email == email).delete()
            users_removed += 1
    if users_removed > 0:
        db.session.commit()
        print(f"Pulizia completata: rimossi interessi di {users_removed} utenti.", file=os.sys.stderr)
def data_collection_job():
    with app.app_context():
        verify_users()
        NOW_UTC = datetime.utcnow()
        BEGIN_DATETIME = NOW_UTC - timedelta(hours=24)
        END_DATETIME = NOW_UTC
        begin_ts = calendar.timegm(BEGIN_DATETIME.timetuple())
        end_ts = calendar.timegm(END_DATETIME.timetuple())
        interests = db.session.query(Interest.airport_code).distinct().all()
        def fetch_flights_from_api(url, headers):
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        for (airport_icao,) in interests:
            flights_collected = 0
            try:
                auth_headers = {"Authorization": f"Bearer {TOKEN}"}
                departures_url = f"{API_BASE_URL}/flights/departure?airport={airport_icao}&begin={begin_ts}&end={end_ts}"
                flights_data_dep = opensky_breaker.call(fetch_flights_from_api, departures_url, auth_headers)
                print(f"Flights collected: {flights_data_dep}", file=os.sys.stderr)
                for f in flights_data_dep:
                    new_flight = Flight(
                        icao24=f.get("icao24"),
                        callsign=f.get("callsign", "").strip() or None,
                        est_departure_airport=f.get("estDepartureAirport"),
                        est_arrival_airport=f.get("estArrivalAirport"),
                        first_seen_utc=datetime.fromtimestamp(f.get("firstSeen")).strftime('%Y-%m-%d %H:%M:%S') if f.get("firstSeen") else None,
                        last_seen_utc=datetime.fromtimestamp(f.get("lastSeen")).strftime('%Y-%m-%d %H:%M:%S') if f.get("lastSeen") else None,
                    )
                    db.session.merge(new_flight)
                    flights_collected += 1
                arrival_url = f"{API_BASE_URL}/flights/arrival?airport={airport_icao}&begin={begin_ts}&end={end_ts}"
                flights_data_arr = opensky_breaker.call(fetch_flights_from_api, arrival_url, auth_headers)
                for f in flights_data_arr:
                    new_flight = Flight(
                        icao24=f.get("icao24"),
                        callsign=f.get("callsign", "").strip() or None,
                        est_departure_airport=f.get("estDepartureAirport"),
                        est_arrival_airport=f.get("estArrivalAirport"),
                        first_seen_utc=datetime.fromtimestamp(f.get("firstSeen")).strftime('%Y-%m-%d %H:%M:%S') if f.get("firstSeen") else None,
                        last_seen_utc=datetime.fromtimestamp(f.get("lastSeen")).strftime('%Y-%m-%d %H:%M:%S') if f.get("lastSeen") else None,
                    )
                    db.session.merge(new_flight)
                    flights_collected += 1
                db.session.commit()
                print(f"Salvati {flights_collected} voli totali per {airport_icao}.", file=os.sys.stderr)
                if flights_collected > 0:
                    publish_flight_count(airport_icao, flights_collected)
            except CircuitBreakerOpenException:
                print(f"[{airport_icao}] Circuit Breaker APERTO. Saltata la raccolta per questo aeroporto.", file=os.sys.stderr)
                db.session.rollback()
                continue
            except Exception as e:
                print(f"Errore non gestito durante la raccolta dati per {airport_icao}: {e}", file=os.sys.stderr)
                db.session.rollback()
                continue
def run_scheduler():
    schedule.every(int(os.environ.get('PERIODO'))).seconds.do(data_collection_job)
    data_collection_job()
    while True:
        schedule.run_pending()
        time.sleep(1)
if __name__ == '__main__':
    TOKEN = get_access_token()
    if TOKEN:
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        app.run(host='0.0.0.0', port=5000, debug=True)
    else:
        print("Errore critico: Impossibile ottenere il token OpenSky. Uscita.", file=os.sys.stderr)