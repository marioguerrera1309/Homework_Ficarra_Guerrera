from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import os
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
class User(db.Model):
    __tablename__ = 'users'
    email = db.Column(db.String(255), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    surname = db.Column(db.String(100), nullable=False)
@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Data Collector is running"}), 200
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)