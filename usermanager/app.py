from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from concurrent import futures
import os
import grpc
import service_pb2
import service_pb2_grpc
import threading
from sqlalchemy import select
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
class User(db.Model):
    __tablename__ = 'users'
    email = db.Column(db.String(255), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    surname = db.Column(db.String(100), nullable=False)
class UserManagerService(service_pb2_grpc.UserManagerServiceServicer):
    def ValidateEmail(self, request, context):
        email=request.email
        print(f"Server: Ricevuta richiesta con utente: {email}", file=os.sys.stderr)
        with app.app_context():
            stmt = select(User).where(User.email == email)
            user = db.session.execute(stmt).scalar_one_or_none()
            if user:
                return service_pb2.Response(validate=True)
            else:
                return service_pb2.Response(validate=False)
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
    users_list = [{"email": user.email, "name": user.name, "surname": user.surname} for user in users]
    return jsonify({"users": users_list}), 200
@app.route('/add_user', methods=['POST'])
def add_user():
    user=User(email=request.form['email'], name=request.form['name'], surname=request.form['surname'])
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "User added successfully"}), 200
@app.route('/delete_user', methods=['POST'])
def delete_user():
    user = User.query.filter_by(email=request.form['email']).first()
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User deleted successfully"}), 200
if __name__ == '__main__':
    grpc_thread = threading.Thread(target=serve, daemon=True)
    grpc_thread.start()
    #print("mainDEBUG: GRPC_PORT =", os.environ.get("GRPC_PORT"))
    app.run(host='0.0.0.0', port=5000, debug=False)