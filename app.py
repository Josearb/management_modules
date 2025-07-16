# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from models import db, User, Product, Sale, Customer, MaintenanceTask, DailySales, init_db
from datetime import datetime
from analytics import analytics_bp
import os
from functools import wraps
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui_12345'
app.register_blueprint(analytics_bp, url_prefix='/analytics')

# Database Configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'erp.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize Database
db.init_app(app)
with app.app_context():
    init_db(app)

# init_db(app)

# Authentication Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor inicie sesión primero', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Por favor inicie sesión primero', 'danger')
                return redirect(url_for('login'))
            user = User.query.get(session['user_id'])
            if user.role != role:
                flash('No tiene permisos para acceder a esta página', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            flash('Inicio de sesión exitoso', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Ha cerrado sesión correctamente', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    modules = []
    
    if session['role'] == 'admin':
        modules = [
            {'name': 'Ventas', 'icon': 'images/sales_icon.png', 'description': 'Gestión de pedidos y facturas', 'route': 'sales'},
            {'name': 'Inventario', 'icon': 'images/inventory_icon.png', 'description': 'Gestión de productos y stock', 'route': 'inventory'},
            # {'name': 'CRM', 'icon': 'images/crm_icon.png', 'description': 'Gestión de clientes y contactos', 'route': 'crm'},
            # {'name': 'Mantenimiento', 'icon': 'images/maintenance.png', 'description': 'Gestión de tareas de mantenimiento', 'route': 'maintenance'},
            {'name': 'Usuarios', 'icon': 'images/users.png', 'description': 'Gestión de usuarios del sistema', 'route': 'users'},
            {'name': 'Analíticas', 'icon': 'images/icons8-analítica-100.png', 'description': 'Estadísticas de ventas', 'route': 'analytics.dashboard'}
        ]
    else:
        modules = [
            {'name': 'Ventas', 'icon': 'images/sales_icon.png', 'description': 'Registro de ventas del día', 'route': 'sales'},
            {'name': 'Inventario', 'icon': 'images/inventory_icon.png', 'description': 'Consulta de productos', 'route': 'inventory'}
        ]
    
    return render_template('dashboard.html', modules=modules)

# Enhanced Sales Module
@app.route('/sales', methods=['GET', 'POST'])
@login_required
def sales():
    if request.method == 'POST':
        try:
            product_id = request.form.get('product_id')
            quantity = int(request.form.get('quantity', 0))
            
            if not product_id or quantity <= 0:
                flash('Debe ingresar una cantidad válida', 'danger')
                return redirect(url_for('sales'))

            product = Product.query.get_or_404(product_id)
            
            if product.quantity < quantity:
                flash(f'Stock insuficiente de {product.name}. Disponible: {product.quantity}', 'danger')
                return redirect(url_for('sales'))

            new_sale = Sale(
                customer="Cliente ocasional",
                total=product.price * quantity,
                date=datetime.utcnow(),
                user_id=session['user_id'],
                product_id=product.id,
                quantity=quantity
            )
            
            product.quantity -= quantity
            product.daily_sales += quantity
            
            db.session.add(new_sale)
            db.session.commit()
            flash('Venta registrada exitosamente', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar venta: {str(e)}', 'danger')
        
        return redirect(url_for('sales'))
    
    # GET request
    products = Product.query.order_by(Product.name).all()
    
    # Obtener actividades para el chatter
    chatter_activities = db.session.query(
        Sale, User, Product
    ).join(
        User, User.id == Sale.user_id
    ).join(
        Product, Product.id == Sale.product_id
    ).order_by(
        Sale.date.desc()
    ).limit(50).all()
    
    # Calcular total acumulado del turno
    today_total = db.session.query(db.func.sum(Sale.total)).filter(
        db.func.date(Sale.date) == datetime.utcnow().date()
    ).scalar() or 0
    
    return render_template('sales.html', 
                         products=products,
                         chatter_activities=chatter_activities,
                         current_date=datetime.utcnow().date(),
                         today_total=today_total)
    
@app.route('/api/sales', methods=['POST'])
@login_required
def api_create_sale():
    try:
        sales_data = request.get_json()
        customer = sales_data.get('customer', 'Cliente ocasional')
        items = sales_data['items']
        
        if not items:
            return jsonify({'success': False, 'message': 'No items selected'})
        
        # Process each item in the sale
        for item in items:
            product = Product.query.get(item['product_id'])
            quantity = int(item['quantity'])
            
            if quantity <= 0:
                continue
            
            if product.quantity < quantity:
                return jsonify({
                    'success': False,
                    'message': f'Insufficient stock for {product.name}. Available: {product.quantity}'
                })
            
            # Update inventory
            product.quantity -= quantity
            product.daily_sales += quantity
            
            # Record sale
            new_sale = Sale(
                customer="Cliente ocasional",
                total=product.price * quantity,
                date=datetime.utcnow(), 
                user_id=session['user_id'],
                product_id=product.id,
                quantity=quantity
            )
            db.session.add(new_sale)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Sale recorded successfully',
            'new_stock': {product.id: product.quantity for product in Product.query.all()}
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/sales/<int:sale_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def api_delete_sale(sale_id):
    try:
        sale = Sale.query.get_or_404(sale_id)
        product = Product.query.get(sale.product_id)
        
        # Restore inventory
        product.quantity += sale.quantity
        product.daily_sales -= sale.quantity
        
        db.session.delete(sale)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Sale deleted and inventory restored',
            'new_stock': product.quantity
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/sales/reset', methods=['POST'])
@login_required
def reset_daily_sales():
    try:
        today = datetime.utcnow().date()

        # Calcular total del día antes de eliminar
        today_total = db.session.query(db.func.sum(Sale.total)).filter(
            db.func.date(Sale.date) == today
        ).scalar() or 0

        # Crear registro histórico
        if today_total > 0:
            new_daily_record = DailySales(
                date=today,
                total=today_total,
                user_id=session['user_id']
            )
            db.session.add(new_daily_record)

        # Eliminar ventas del día
        db.session.query(Sale).filter(
            db.func.date(Sale.date) == today
        ).delete()

        # Resetear contadores diarios
        db.session.query(Product).update({'daily_sales': 0})

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Contadores y ventas del día reiniciados. Total registrado: $%.2f' % today_total
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error al reiniciar: {str(e)}'
        }), 500


@app.route('/sales/report')
@login_required
def print_daily_report():
    # Get products sold today (daily_sales > 0)
    products_sold = Product.query.filter(Product.daily_sales > 0).all()
    total_sales = sum(p.price * p.daily_sales for p in products_sold)
    
    return render_template('sales_report.html',
                        products=products_sold,
                        total=total_sales,
                        date=datetime.now().strftime("%d/%m/%Y"))

# Inventory Module
@app.route('/inventory', methods=['GET', 'POST'])
@login_required
def inventory():
    if request.method == 'POST' and session['role'] == 'admin':
        try:
            new_product = Product(
                name=request.form['name'],
                quantity=int(request.form['quantity']),
                price=float(request.form['price']),
                daily_sales=0
            )
            db.session.add(new_product)
            db.session.commit()
            flash('Producto agregado exitosamente', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al agregar producto: {str(e)}', 'danger')
        return redirect(url_for('inventory'))
    
    products = Product.query.order_by(Product.name).all()
    return render_template('inventory.html', products=products)

@app.route('/inventory/delete/<int:product_id>')
@login_required
@role_required('admin')
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    try:
        # Eliminar primero las ventas asociadas
        Sale.query.filter_by(product_id=product_id).delete()
        # Luego eliminar el producto
        db.session.delete(product)
        db.session.commit()
        flash('Producto y sus ventas asociadas eliminados correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar producto: {str(e)}', 'danger')
    return redirect(url_for('inventory'))

@app.route('/inventory/update/<int:product_id>', methods=['POST'])
@login_required
@role_required('admin')
def update_product(product_id):
    product = Product.query.get_or_404(product_id)
    try:
        product.name = request.form['name']
        product.quantity = int(request.form['quantity'])
        product.price = float(request.form['price'])
        db.session.commit()
        flash('Producto actualizado correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar producto: {str(e)}', 'danger')
    return redirect(url_for('inventory'))

# CRM Module
@app.route('/crm', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def crm():
    if request.method == 'POST':
        try:
            new_customer = Customer(
                name=request.form['name'],
                email=request.form['email'],
                phone=request.form['phone']
            )
            db.session.add(new_customer)
            db.session.commit()
            flash('Cliente agregado exitosamente', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al agregar cliente: {str(e)}', 'danger')
        return redirect(url_for('crm'))
    
    customers = Customer.query.order_by(Customer.name).all()
    return render_template('crm.html', customers=customers)

@app.route('/crm/update/<int:customer_id>', methods=['POST'])
@login_required
@role_required('admin')
def update_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    try:
        customer.name = request.form['name']
        customer.email = request.form['email']
        customer.phone = request.form['phone']
        db.session.commit()
        flash('Cliente actualizado correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar cliente: {str(e)}', 'danger')
    return redirect(url_for('crm'))

@app.route('/crm/delete/<int:customer_id>')
@login_required
@role_required('admin')
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    try:
        db.session.delete(customer)
        db.session.commit()
        flash('Cliente eliminado correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar cliente: {str(e)}', 'danger')
    return redirect(url_for('crm'))

# Maintenance Module
@app.route('/maintenance', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def maintenance():
    if request.method == 'POST':
        try:
            new_task = MaintenanceTask(
                equipment=request.form['equipment'],
                description=request.form['description'],
                priority=request.form['priority'],
                assigned_to=request.form['assigned_to'],
                due_date=request.form['due_date']
            )
            db.session.add(new_task)
            db.session.commit()
            flash('Tarea de mantenimiento creada exitosamente', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear tarea: {str(e)}', 'danger')
        return redirect(url_for('maintenance'))
    
    tasks = MaintenanceTask.query.order_by(MaintenanceTask.priority, MaintenanceTask.due_date).all()
    return render_template('maintenance.html', tasks=tasks)

@app.route('/maintenance/update/<int:task_id>', methods=['POST'])
@login_required
@role_required('admin')
def update_task(task_id):
    task = MaintenanceTask.query.get_or_404(task_id)
    try:
        task.equipment = request.form['equipment']
        task.description = request.form['description']
        task.priority = request.form['priority']
        task.status = request.form['status']
        task.assigned_to = request.form['assigned_to']
        task.due_date = request.form['due_date']
        db.session.commit()
        flash('Tarea actualizada correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar tarea: {str(e)}', 'danger')
    return redirect(url_for('maintenance'))

@app.route('/maintenance/complete/<int:task_id>')
@login_required
@role_required('admin')
def complete_task(task_id):
    task = MaintenanceTask.query.get_or_404(task_id)
    try:
        task.status = 'Completado'
        db.session.commit()
        flash('Tarea marcada como completada', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al completar tarea: {str(e)}', 'danger')
    return redirect(url_for('maintenance'))

@app.route('/maintenance/delete/<int:task_id>')
@login_required
@role_required('admin')
def delete_task(task_id):
    task = MaintenanceTask.query.get_or_404(task_id)
    try:
        db.session.delete(task)
        db.session.commit()
        flash('Tarea eliminada correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar tarea: {str(e)}', 'danger')
    return redirect(url_for('maintenance'))


# Users Module
@app.route('/users', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def users():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        
        if User.query.filter_by(username=username).first():
            flash('El nombre de usuario ya existe', 'danger')
        else:
            try:
                new_user = User(username=username, role=role)
                new_user.set_password(password)
                db.session.add(new_user)
                db.session.commit()
                flash('Usuario creado exitosamente', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error al crear usuario: {str(e)}', 'danger')
        return redirect(url_for('users'))
    
    users = User.query.order_by(User.role, User.username).all()
    return render_template('users.html', users=users)

@app.route('/users/delete/<int:user_id>')
@login_required
@role_required('admin')
def delete_user(user_id):
    if user_id == session['user_id']:
        flash('No puedes eliminarte a ti mismo', 'danger')
    else:
        user = User.query.get_or_404(user_id)
        try:
            Sale.query.filter_by(user_id=user_id).delete()
            db.session.delete(user)
            db.session.commit()
            flash('Usuario eliminado correctamente', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al eliminar usuario: {str(e)}', 'danger')
    return redirect(url_for('users'))

@app.route('/sales/report/pdf')
@login_required
def download_sales_pdf():
    # Obtener productos vendidos hoy
    products_sold = Product.query.filter(Product.daily_sales > 0).all()
    total_sales = sum(p.price * p.daily_sales for p in products_sold)
    current_date = datetime.now().strftime("%d/%m/%Y")
    
    # Crear buffer para el PDF
    buffer = BytesIO()
    
    # Crear documento PDF
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Contenido del PDF
    elements = []
    
    # Título
    elements.append(Paragraph(f"Reporte de Ventas - {current_date}", styles['Title']))
    elements.append(Paragraph("Tradyx", styles['Normal']))
    elements.append(Paragraph(" ", styles['Normal']))  # Espacio
    
    # Datos de la tabla
    data = [["#", "Producto", "Cantidad", "Precio Unit.", "Subtotal"]]
    
    for idx, product in enumerate(products_sold, 1):
        data.append([
            str(idx),
            product.name,
            str(product.daily_sales),
            f"${product.price:.2f}",
            f"${product.price * product.daily_sales:.2f}"
        ])
    
    # Total
    data.append(["", "", "", "Total:", f"${total_sales:.2f}"])
    
    # Crear tabla
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, -1), (-2, -1), colors.lightgrey),
        ('BACKGROUND', (-1, -1), (-1, -1), colors.grey),
        ('TEXTCOLOR', (-1, -1), (-1, -1), colors.whitesmoke),
    ]))
    
    elements.append(table)
    
    # Generar PDF
    doc.build(elements)
    
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"reporte_ventas_{current_date.replace('/', '-')}.pdf",
        mimetype='application/pdf'
    )

if __name__ == '__main__':
    app.run(debug=True)