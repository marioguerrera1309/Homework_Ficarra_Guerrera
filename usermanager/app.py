from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from concurrent import futures
import os
import grpc
import service_pb2
import service_pb2_grpc
import threading
from sqlalchemy import select
from datetime import datetime, timedelta
import schedule
import time
import json
import hashlib
from sqlalchemy.exc import IntegrityError
from prometheus_client import start_http_server, Counter, Gauge

L_LABELS = ['service', 'node_name']
MY_SERVICE = "usermanager"
MY_NODE = os.environ.get('NODE_NAME', 'docker-desktop')
USER_OPS_COUNTER = Counter('usermanager_ops_total', 'Conteggio totale operazioni utente', L_LABELS)
DB_LATENCY_GAUGE = Gauge('usermanager_db_latency_seconds', 'Tempo ultima operazione DB', L_LABELS)
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
class User(db.Model):
    __tablename__ = 'users'
    email = db.Column(db.String(255), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    surname = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
class IdempotencyKey(db.Model):
    __tablename__ = 'idempotency_keys'
    key = db.Column(db.String(255), primary_key=True)
    status_code = db.Column(db.Integer, nullable=True)
    response_body = db.Column(db.Text, nullable=True)
    completion_time = db.Column(db.DateTime, default=datetime.utcnow)
class UserManagerService(service_pb2_grpc.UserManagerServiceServicer):
    def CheckUserStatus(self, request, context):
        email=request.email
        print(f"Server: Ricevuta richiesta con utente: {email}", file=os.sys.stderr)
        with app.app_context():
            stmt = select(User).where(User.email == email)
            user = db.session.execute(stmt).scalar_one_or_none()
            if user is None:
                return service_pb2.Response(
                    status=service_pb2.UserStatus.NOT_FOUND
                )
            if user.is_active:
                return service_pb2.Response(
                    status=service_pb2.UserStatus.ACTIVE
                )
            else:
                return service_pb2.Response(
                    status=service_pb2.UserStatus.DELETED
                )
def serve():
    try:
        #print(f"Server started at :{os.environ.get('GRPC_PORT')}")
        #print("DEBUG: GRPC_PORT =", os.environ.get("GRPC_PORT"))
        server=grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        service_pb2_grpc.add_UserManagerServiceServicer_to_server(UserManagerService(), server)
        server.add_insecure_port(f"[::]:{os.environ.get('GRPC_PORT')}")
        server.start()
        print(f"Server started at :{os.environ.get('GRPC_PORT')}")
        server.wait_for_termination()
    except Exception as e:
        print("ERRORE nel thread GRPC:", e)
@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "User Manager is running"}), 200
@app.route('/users', methods=['GET'])
def users():
    users= db.session.execute(db.select(User).order_by(User.email)).scalars()
    if users is None:
        return jsonify({"message": "No users found"}), 200
    else:
        users_list = [{"email": user.email, "name": user.name, "surname": user.surname, "is_active": user.is_active, "deleted_at": user.deleted_at} for user in users]
        return jsonify({"users": users_list}), 200
@app.route('/add_user', methods=['POST'])
def add_user():
    #idempotency_key = request.headers.get('X-Idempotency-Key')
    USER_OPS_COUNTER.labels(service=MY_SERVICE, node_name=MY_NODE).inc()
    start_time = time.time()
    email = request.form.get('email')
    name = request.form.get('name')
    surname = request.form.get('surname')
    idempotency_key = hashlib.sha256(email.encode('utf-8')).hexdigest()
    if email is None or name is None or surname is None:
        return jsonify({"error": "Parametri mancanti."}), 400
    existing_key = IdempotencyKey.query.filter_by(key=idempotency_key).first()
    if existing_key:
        print(f"Richiesta duplicata intercettata con chiave: {idempotency_key}. Restituzione risposta cache.")
        return jsonify({"message": "Richiesta duplicata intercettata", "key": idempotency_key}), 200
    success_message = {"message": "User added successfully"}
    success_status = 201
    try:
        new_user = User(email=email, name=name, surname=surname)
        db.session.add(new_user)
        new_key = IdempotencyKey(
            key=idempotency_key,
            status_code=success_status,
            response_body=json.dumps(success_message)
        )
        db.session.add(new_key)
        db.session.commit()
        latency = time.time() - start_time
        DB_LATENCY_GAUGE.labels(service=MY_SERVICE, node_name=MY_NODE).set(latency)
        return jsonify(success_message), success_status
    except IntegrityError:
        db.session.rollback()
        error_response = {"error": "User with this email already exists."}
        error_status = 409
        return jsonify(error_response), error_status
    except Exception as e:
        db.session.rollback()
        print(f"Errore durante l'aggiunta utente: {e}")
        return jsonify({"error": "Internal server error."}), 500
@app.route('/delete_user', methods=['POST'])
def delete_user():
    USER_OPS_COUNTER.labels(service=MY_SERVICE, node_name=MY_NODE).inc()
    user = User.query.filter_by(email=request.form['email']).first()
    if user is None:
        return jsonify({"message": "User not found."}), 404
    else:
        user.is_active = False
        user.deleted_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"message": "User deleted successfully (Soft Delete)"}), 200
def hard_delete_user():
    with app.app_context():
        deleted_count = 0
        #print(f"Hard delete {threshold_time}", file=os.sys.stderr)
        users= db.session.execute(db.select(User).order_by(User.email)).scalars()
        for user in users:
            if user.is_active == False:
                db.session.delete(user)
                deleted_count += 1
        # deleted_count = db.session.query(User).filter(
        #     User.is_active == False,
        #     User.deleted_at <= threshold_time
        # ).delete(synchronize_session=False)
        db.session.commit()
        if deleted_count > 0:
            print(f"[HARD DELETE] Rimossi definitivamente {deleted_count} utenti obsoleti.", file=os.sys.stderr)
def run_hard_delete_user():
    schedule.every(int(os.environ.get('PERIODO'))).seconds.do(hard_delete_user)
    #print(f"[HARD DELETE]", file=os.sys.stderr)
    hard_delete_user()
    while True:
        schedule.run_pending()
        time.sleep(1)
def delete_idempotency_key():
    five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
    with app.app_context():
        rows_deleted = (
            db.session.query(IdempotencyKey)
            .filter(IdempotencyKey.completion_time < five_minutes_ago)
            .delete(synchronize_session='fetch')
        )
        db.session.commit()
        #print(f"Cancellate {rows_deleted} chiavi di idempotenza più vecchie di 5 minuti.", file=os.sys.stderr)
def run_delete_idempotency_key():
    schedule.every(int(os.environ.get('PERIODO'))).seconds.do(delete_idempotency_key)
    #print(f"[HARD DELETE]", file=os.sys.stderr)
    while True:
        schedule.run_pending()
        time.sleep(1)
if __name__ == '__main__':
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        start_http_server(8000)
        print("Prometheus metrics available on port 8000")
        grpc_thread = threading.Thread(target=serve, daemon=True)
        grpc_thread.start()
        hard_delete_thread = threading.Thread(target=run_hard_delete_user, daemon=True)
        hard_delete_thread.start()
        delete_idempotency_key_thread = threading.Thread(target=run_delete_idempotency_key, daemon=True)
        delete_idempotency_key_thread.start()
        #print("mainDEBUG: GRPC_PORT =", os.environ.get("GRPC_PORT"))
    app.run(host='0.0.0.0', port=5000, debug=False)