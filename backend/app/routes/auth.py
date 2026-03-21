import jwt
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, Blueprint

app = Flask(__name__)

# Configurations
app.config['SECRET_KEY'] = 'your_secret_key'

# Creating a blueprint for authentication
auth_bp = Blueprint('auth', __name__)

# Sample user storage (use a database in production)
users = {}

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if username in users:
        return jsonify({'message': 'User already exists!'}), 409
    users[username] = {'password': password}
    return jsonify({'message': 'User registered successfully!'}), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    user = users.get(username)
    if user and user['password'] == password:
        token = jwt.encode({'username': username, 'exp': datetime.utcnow() + timedelta(hours=1)}, app.config['SECRET_KEY'])
        return jsonify({'token': token}), 200
    return jsonify({'message': 'Invalid credentials!'}), 401

app.register_blueprint(auth_bp, url_prefix='/auth')

if __name__ == '__main__':
    app.run(debug=True)
