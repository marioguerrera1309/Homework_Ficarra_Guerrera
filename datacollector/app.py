from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import os
from opensky_api import OpenSkyApi
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
opensky_api = OpenSkyApi(username=OPENSKY_USERNAME, password=OPENSKY_PASSWORD)
@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Data Collector is running"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)