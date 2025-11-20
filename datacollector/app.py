from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import os
from opensky_api import OpenSkyApi
import time
import json
from datetime import datetime, timedelta
import calendar
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
opensky_api = OpenSkyApi(username=os.environ.get('USERNAME_API'), password=os.environ.get('PASSWORD_API'))
@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Data Collector is running", "username": os.environ.get('USERNAME_API')}), 200
@app.route('/flights', methods=['GET'])
def flights():
    AIRPORT_ICAO = "EDDF"
    NOW_UTC = datetime.utcnow()
    BEGIN_DATETIME = NOW_UTC - timedelta(hours=1)
    END_DATETIME = NOW_UTC
    begin_ts = calendar.timegm(BEGIN_DATETIME.timetuple())
    end_ts = calendar.timegm(END_DATETIME.timetuple())
    voli_json_list = []
    print(f"Recupero partenze da {AIRPORT_ICAO} (TS: {begin_ts} a {end_ts})...", file=os.sys.stderr)
    try:
        flights = opensky_api.get_departures_by_airport(AIRPORT_ICAO, begin_ts, end_ts)
        if flights:
            for f in flights:
                volo_dati = {
                    "icao24": f.icao24,
                    "callsign": f.callsign.strip() if f.callsign else None,
                    "firstSeen_timestamp": f.firstSeen,
                    "lastSeen_timestamp": f.lastSeen,
                    "estDepartureAirport": AIRPORT_ICAO,
                    "estArrivalAirport": f.estArrivalAirport if f.estArrivalAirport else None,
                    "firstSeen_utc": datetime.fromtimestamp(f.firstSeen).strftime('%Y-%m-%d %H:%M:%S'),
                    "lastSeen_utc": datetime.fromtimestamp(f.lastSeen).strftime('%Y-%m-%d %H:%M:%S'),
                }
                voli_json_list.append(volo_dati)
            output_data = {
                "query_info": {
                    "airport_icao": AIRPORT_ICAO,
                    "start_time_ts": begin_ts,
                    "end_time_ts": end_ts,
                    "count": len(voli_json_list)
                },
                "flights": voli_json_list
            }
            return jsonify(output_data), 200
        else:
            print("Nessun volo in partenza trovato.", file=os.sys.stderr)
            return jsonify({
                "query_info": {
                    "airport_icao": AIRPORT_ICAO,
                    "count": 0,
                    "message": "No flights found in the last 24 hours."
                },
                "flights": []
            }), 200

    except Exception as e:
        print(f"ERRORE API/Rete: {e}", file=os.sys.stderr)
        error_msg = {"error": "OpenSky API Error", "message": str(e)}
        return jsonify(error_msg), 503
@app.route('/realtime', methods=['GET'])
def get_realtime_states():
    BBOX_FRANKFURT = (49.5, 51.5, 7.5, 10.5)
    """
    Recupera i vettori di stato in tempo reale attorno a EDDF (non richiede autenticazione).
    Questo serve come test di connettività.
    """
    print(f"Recupero stati di volo in tempo reale (BBOX: {BBOX_FRANKFURT})...", file=os.sys.stderr)
    try:
        # get_states non richiede autenticazione per i dati non filtrati
        states_data = opensky_api.get_states(bbox=BBOX_FRANKFURT)
        realtime_list = []
        if states_data and states_data.states:
            for s in states_data.states:
                realtime_list.append({
                    "icao24": s.icao24,
                    "callsign": s.callsign.strip() if s.callsign else None,
                    "origin_country": s.origin_country,
                    "latitude": s.latitude,
                    "longitude": s.longitude,
                    "velocity_ms": s.velocity,
                    "on_ground": s.on_ground
                })
            output_data = {
                "query_type": "Realtime States (Unauthenticated)",
                "area_bbox": BBOX_FRANKFURT,
                "count": len(realtime_list),
                "states": realtime_list
            }
            return jsonify(output_data), 200
        else:
            return jsonify({
                "query_type": "Realtime States (Unauthenticated)",
                "area_bbox": BBOX_FRANKFURT,
                "count": 0,
                "message": "Nessun aereo in tempo reale trovato nell'area specificata (o rate limit anonimo)."
            }), 200
    except Exception as e:
        print(f"ERRORE API/Rete in realtime: {e}", file=os.sys.stderr)
        error_msg = {"error": "OpenSky API Exception", "message": str(e)}
        return jsonify(error_msg), 503
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)