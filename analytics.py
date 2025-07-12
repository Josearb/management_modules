# analytics.py
from flask import Blueprint, render_template
from datetime import datetime, timedelta
from models import Sale, Product, db
from sqlalchemy import func

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/analytics')
def dashboard():
    # KPIs principales
    total_sales = db.session.query(func.sum(Sale.total)).scalar() or 0
    top_products = db.session.query(
        Product.name,
        func.sum(Sale.quantity).label('total_sold')
    ).join(Sale).group_by(Product.name).order_by(func.sum(Sale.quantity).desc()).limit(5).all()

    # Ventas semanales/mensuales
    today = datetime.utcnow().date()
    last_week = today - timedelta(days=7)
    last_month = today - timedelta(days=30)

    weekly_sales = Sale.query.filter(
        Sale.date >= last_week
    ).all()

    monthly_sales = Sale.query.filter(
        Sale.date >= last_month
    ).all()

    # Formatear datos para Chart.js
    def prepare_chart_data(sales):
        dates = sorted({sale.date.strftime('%Y-%m-%d') for sale in sales})
        amounts = [sum(sale.total for sale in sales if sale.date.strftime('%Y-%m-%d') == date) for date in dates]
        return {
            'labels': dates,
            'data': amounts
        }

    return render_template(
        'analytics.html',
        total_sales=total_sales,
        top_products=top_products,
        weekly_data=prepare_chart_data(weekly_sales),
        monthly_data=prepare_chart_data(monthly_sales)
    )