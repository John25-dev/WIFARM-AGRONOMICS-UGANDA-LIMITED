import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv()

app = Flask(__name__)

# Define a base directory for absolute paths
basedir = os.path.abspath(os.path.dirname(__file__))
default_db_path = 'sqlite:///' + os.path.join(basedir, 'prod_business.db')

# Securely load the Database URI from environment variables
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', default_db_path)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Enable ProxyFix to handle Cloudflare and Apache reverse proxy headers correctly
app.proxy_fix = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# --- Database Models ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    role = db.Column(db.String(20), default='Employee')  # Admin, Manager, Employee
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'))

class Branch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(120), nullable=False)
    stocks = db.relationship('Stock', backref='branch', lazy=True)

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    min_required = db.Column(db.Integer, default=5)
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'))

class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    identity_code = db.Column(db.String(50), unique=True, nullable=False)
    asset_class = db.Column(db.String(50)) # e.g., Vehicle, Equipment
    description = db.Column(db.Text)

class EmployeeLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    location_data = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class ClientRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(100))
    animal_count = db.Column(db.Integer)
    medication_history = db.Column(db.Text)
    assigned_employee_id = db.Column(db.Integer, db.ForeignKey('user.id'))

# --- API Endpoints ---

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    """Filters discrepancies instantly (where quantity < min_required)."""
    branch_id = request.args.get('branch_id')
    query = Stock.query
    if branch_id:
        query = query.filter_by(branch_id=branch_id)
    
    items = query.all()
    return jsonify([{
        "id": i.id,
        "name": i.item_name,
        "quantity": i.quantity,
        "discrepancy": i.quantity < i.min_required,
        "branch": i.branch.location
    } for i in items])

@app.route('/api/inventory/request', methods=['POST'])
def request_stock():
    """Allows employees to request/update stock levels."""
    data = request.get_json()
    stock_item = Stock.query.filter_by(item_name=data['name'], branch_id=data['branch_id']).first()
    if stock_item:
        stock_item.quantity += data['amount']
        db.session.commit()
        return jsonify({"message": "Stock updated successfully"})
    return jsonify({"error": "Item not found"}), 404

@app.route('/api/employee/track', methods=['POST'])
def log_location():
    """Records daily location of employees."""
    data = request.get_json()
    new_log = EmployeeLog(user_id=data['user_id'], location_data=data['location'])
    db.session.add(new_log)
    db.session.commit()
    return jsonify({"status": "Location logged"})

@app.route('/api/clients', methods=['POST', 'GET'])
def manage_clients():
    """Feeds in client data: animal count, medication, etc."""
    if request.method == 'POST':
        data = request.get_json()
        new_client = ClientRecord(
            client_name=data['name'],
            animal_count=data['animal_count'],
            medication_history=data['medication'],
            assigned_employee_id=data['employee_id']
        )
        db.session.add(new_client)
        db.session.commit()
        return jsonify({"status": "Client record updated"})
    
    records = ClientRecord.query.all()
    return jsonify([{
        "name": r.client_name,
        "animals": r.animal_count,
        "medication": r.medication_history
    } for r in records])

@app.route('/api/assets', methods=['GET', 'POST'])
def manage_assets():
    """Capture assets by identity and class without repetition."""
    if request.method == 'POST':
        data = request.get_json()
        # Check for repetition
        if Asset.query.filter_by(identity_code=data['id_code']).first():
            return jsonify({"error": "Asset identity already exists"}), 400
        
        asset = Asset(identity_code=data['id_code'], asset_class=data['class'], description=data['desc'])
        db.session.add(asset)
        db.session.commit()
        return jsonify({"status": "Asset captured"})
    return jsonify([{"code": a.identity_code, "class": a.asset_class} for a in Asset.query.all()])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Seed data if empty
        if not Branch.query.first():
            b1 = Branch(location="North Branch")
            db.session.add(b1)
            db.session.flush()
            db.session.add(Stock(item_name="Antibiotics", quantity=2, branch_id=b1.id))
            db.session.add(User(username="AdminUser", role="Admin"))
            db.session.commit()
    # Debug mode disabled for production security
    app.run(host='0.0.0.0', port=5000, debug=False)