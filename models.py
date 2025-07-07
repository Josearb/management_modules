from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime  # Importación faltante

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'user'  # Nombre explícito de tabla
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    
    def set_password(self, password):
        self.password = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password, password)

class Product(db.Model):
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    daily_sales = db.Column(db.Integer, default=0)
    
    def actual_sales_today(self):
        return sum(sale.quantity for sale in self.product_sales if  # Cambiado a product_sales
                 sale.date.startswith(datetime.now().strftime("%Y-%m-%d")))

class Sale(db.Model):
    __tablename__ = 'sale'
    id = db.Column(db.Integer, primary_key=True)
    customer = db.Column(db.String(100), nullable=False)
    total = db.Column(db.Float, nullable=False)
    date = db.Column(db.String(20), nullable=False)  # Considera usar DateTime
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    
    # Relaciones con nombres explícitos
    user = db.relationship('User', backref=db.backref('user_sales', lazy=True))
    product = db.relationship('Product', backref=db.backref('product_sales', lazy=True))

class DailySales(db.Model):
    __tablename__ = 'daily_sales'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)  # Considera usar Date
    total = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Añadido

class Customer(db.Model):
    __tablename__ = 'customer'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)

class MaintenanceTask(db.Model):
    __tablename__ = 'maintenance_task'
    id = db.Column(db.Integer, primary_key=True)
    equipment = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='Pendiente')
    assigned_to = db.Column(db.String(100), nullable=False)
    due_date = db.Column(db.String(20), nullable=False)  # Considera usar DateTime

def init_db(app):
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
