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
from datetime import datetime, timedelta
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
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
class User(db.Model):
    __tablename__ = 'users'
    email = db.Column(db.String(255), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    surname = db.Column(db.String(100), nullable=False)
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
API_BASE_URL = "https://opensky-network.org/api"
AIRPORT_ICAO = "OMDB"
TOKEN=None
SERVER_ADDRESS='usermanager:'+os.environ.get('GRPC_PORT')
def UserVerification(email):
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub=service_pb2_grpc.UserManagerServiceStub(channel)
        print(f"Client: invio la richiesta con email: {email}", file=os.sys.stderr)
        response=stub.ValidateEmail(service_pb2.UserVerification(email=email))
        print(f"Client: Invio", file=os.sys.stderr)
        validate=response.validate
        print(f"Ricevuta risposta: {validate}", file=os.sys.stderr)
        return validate

def get_access_token():
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
        return None
@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Data Collector is running"}), 200
@app.route('/flights', methods=['POST'])
def flights():
    data = request.get_json()
    email = data['email']
    results = db.session.query(Interest.airport_code) \
        .join(User) \
        .filter(User.email == email) \
        .all()
    airport_codes = [code[0] for code in results]
    NOW_UTC = datetime.utcnow()
    BEGIN_DATETIME = NOW_UTC - timedelta(hours=24)
    END_DATETIME = NOW_UTC
    begin_ts = calendar.timegm(BEGIN_DATETIME.timetuple())
    end_ts = calendar.timegm(END_DATETIME.timetuple())
    auth_headers = {"Authorization": f"Bearer {TOKEN}"}
    for code in airport_codes:
        departures_url = f"{API_BASE_URL}/flights/departure?airport={code}&begin={begin_ts}&end={end_ts}"
        print(f"Query in corso: {departures_url}", file=os.sys.stderr)
        try:
            response = requests.get(departures_url, headers=auth_headers)
            response.raise_for_status()
            flights = response.json()
        except requests.exceptions.RequestException as e:
            print(f"ERRORE API/Rete: {e}", file=os.sys.stderr)
            error_msg = {"error": "OpenSky API Error", "message": str(e)}
            return jsonify(error_msg), 503
'''
@app.route('/flights', methods=['GET'])
def flights():
    NOW_UTC = datetime.utcnow()
    BEGIN_DATETIME = NOW_UTC - timedelta(hours=24)
    END_DATETIME = NOW_UTC
    begin_ts = calendar.timegm(BEGIN_DATETIME.timetuple())
    end_ts = calendar.timegm(END_DATETIME.timetuple())
    auth_headers = {"Authorization": f"Bearer {TOKEN}"}
    departures_url = f"{API_BASE_URL}/flights/departure?airport={AIRPORT_ICAO}&begin={begin_ts}&end={end_ts}"
    print(f"Query in corso: {departures_url}", file=os.sys.stderr)
    try:
        response = requests.get(departures_url, headers=auth_headers)
        response.raise_for_status()
        flights = response.json()
        voli_json_list = []
        if flights:
            for f in flights:
                volo_dati = {
                    "icao24": f.get("icao24"),
                    "callsign": f.get("callsign", "").strip() or None,
                    "firstSeen_timestamp": f.get("firstSeen"),
                    "lastSeen_timestamp": f.get("lastSeen"),
                    "estDepartureAirport": f.get("estDepartureAirport"),
                    "estArrivalAirport": f.get("estArrivalAirport"),
                    "firstSeen_utc": datetime.fromtimestamp(f.get("firstSeen")).strftime('%Y-%m-%d %H:%M:%S') if f.get("firstSeen") else None,
                    "lastSeen_utc": datetime.fromtimestamp(f.get("lastSeen")).strftime('%Y-%m-%d %H:%M:%S') if f.get("lastSeen") else None,
                }
                voli_json_list.append(volo_dati)
            output_data = {
                "query_info": {
                    "airport_icao": airport_icao,
                    "start_time_ts": begin_ts,
                    "end_time_ts": end_ts,
                    "count": len(voli_json_list)
                },
                "flights": voli_json_list
            }
            return jsonify(output_data), 200
        else:
            message = f"Nessun volo trovato da {begin_ts} a {end_ts} (UTC)."
            print(message, file=os.sys.stderr)
            return jsonify({
                "informazioni_query": {
                    "aeroporto_icao": AIRPORT_ICAO,
                    "numero_risultati": 0,
                    "messaggio": message
                },
                "voli": []
            }), 200
    except requests.exceptions.RequestException as e:
        print(f"ERRORE API/Rete: {e}", file=os.sys.stderr)
        error_msg = {"error": "OpenSky API Error", "message": str(e)}
        return jsonify(error_msg), 503
'''
@app.route('/add_interest', methods=['POST'])
def add_interest():
    data = request.get_json()
    email=data.get("email")
    #email="prova@prova.it"
    airport=data.get("airport", [])
    x=UserVerification(email)
    #print(f"x: {x}", file=os.sys.stderr)
    if x:
        for index, a in enumerate(airport):
            y=Interest(email=email, airport_code=a)
            db.session.add(y)
            db.session.commit()
            print(f"{index}: {a} : interesse inserito in db", file=os.sys.stderr)
        return jsonify({"message": f"Utente {email} verificato e {len(airport)} interessi aggiunti."}), 200
    else:
        print(f"L'utente non esiste", file=os.sys.stderr)
        return jsonify({"message": "L'utente non esiste"}), 200
@app.route('/interest', methods=['POST'])
def interest():
    data = request.get_json()
    email=data.get("email")
    x=UserVerification(email)
    if x:
        int= db.session.scalars(db.select(Interest).where(Interest.email == email)).all()
        int_list = [{"email": i.email, "airport_code": i.airport_code} for i in int]
        return jsonify({"Interest": int_list}), 200
    else:
        print(f"L'utente non esiste", file=os.sys.stderr)
        return jsonify({"message": "L'utente non esiste"}), 200
if __name__ == '__main__':
    TOKEN = get_access_token()
    app.run(host='0.0.0.0', port=5000, debug=True)