from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import os
import requests
import json
import calendar
from datetime import datetime, timedelta
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
class Flight(db.Model):
    _tablename_ = 'flights'
    code = db.Column(db.String(50), primary_key=True)
    airport_code = db.Column(db.String(10), nullable=False)
    country = db.Column(db.String(100), nullable=False)
class Interest(db.Model):
    _tablename_ = 'interests'
    email = db.Column(db.String(255), primary_key=True)
    airport_code = db.Column(db.String(10), primary_key=True)
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
API_BASE_URL = "https://opensky-network.org/api"
AIRPORT_ICAO = "OMDB"
TOKEN=None
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
                    "nominativo": f.get("callsign", "").strip() or None,
                    "primo_avvistamento_ts": f.get("firstSeen"),
                    "ultimo_avvistamento_ts": f.get("lastSeen"),
                    "aeroporto_partenza_stimato": f.get("estDepartureAirport"),
                    "aeroporto_arrivo_stimato": f.get("estArrivalAirport"),
                    "primo_avvistamento_utc": datetime.fromtimestamp(f.get("firstSeen")).strftime('%Y-%m-%d %H:%M:%S') if f.get("firstSeen") else None,
                    "ultimo_avvistamento_utc": datetime.fromtimestamp(f.get("lastSeen")).strftime('%Y-%m-%d %H:%M:%S') if f.get("lastSeen") else None,
                }
                voli_json_list.append(volo_dati)
            output_data = {
                "informazioni_query": {
                    "aeroporto_icao": AIRPORT_ICAO,
                    "inizio_ts": begin_ts,
                    "fine_ts": end_ts,
                    "numero_risultati": len(voli_json_list)
                },
                "voli": voli_json_list
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
if __name__ == '__main__':
    TOKEN = get_access_token()
    app.run(host='0.0.0.0', port=5000, debug=True)