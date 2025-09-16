from flask import Flask, render_template, request, redirect, url_for, flash, send_file, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import csv
import io
from models import db, Person, InventoryItem, User, AuditLog
import os
import socket
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-replace-this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Decorator to restrict routes to admin users
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('You do not have permission to perform this action.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def log_action(action, model_type, model_id, user_id, details=None):
    audit = AuditLog(
        action=action,
        model_type=model_type,
        model_id=model_id,
        user_id=user_id,
        details=details
    )
    db.session.add(audit)
    db.session.commit()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            log_action('login', 'User', user.id, user.id, f'User {username} logged in')
            return redirect(url_for('index'))
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    user_id = current_user.id
    username = current_user.username
    logout_user()
    log_action('logout', 'User', user_id, user_id, f'User {username} logged out')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    recent_changes = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()
    total_items = InventoryItem.query.count()
    total_people = Person.query.count()
    recent_changes_with_users = []
    for change in recent_changes:
        user = User.query.get(change.user_id)
        recent_changes_with_users.append({
            'action': change.action,
            'model_type': change.model_type,
            'details': change.details,
            'username': user.username if user else 'Unknown',
            'timestamp': change.timestamp
        })
    return render_template('index.html', recent_changes=recent_changes_with_users, total_items=total_items, total_people=total_people, user_role=current_user.role)

@app.route('/employees', methods=['GET', 'POST'])
@login_required
def employees():
    search_query = request.form.get('search', '') if request.method == 'POST' else ''
    query = Person.query
    if search_query:
        query = query.filter(
            (Person.first_name.ilike(f'%{search_query}%')) |
            (Person.last_name.ilike(f'%{search_query}%')) |
            (Person.email.ilike(f'%{search_query}%')) |
            (Person.department.ilike(f'%{search_query}%'))
        )
    people = query.all()
    return render_template('employees.html', people=people, search_query=search_query, user_role=current_user.role)

@app.route('/users', methods=['GET', 'POST'])
@admin_required
def users():
    search_query = request.form.get('search', '') if request.method == 'POST' else ''
    query = User.query
    if search_query:
        query = query.filter(
            (User.username.ilike(f'%{search_query}%')) |
            (User.role.ilike(f'%{search_query}%'))
        )
    users = query.all()
    return render_template('users.html', users=users, search_query=search_query)

@app.route('/assets', methods=['GET', 'POST'])
@login_required
def assets():
    search_query = request.form.get('search', '') if request.method == 'POST' else ''
    query = InventoryItem.query
    if search_query:
        query = query.join(Person, isouter=True).filter(
            (InventoryItem.item_type.ilike(f'%{search_query}%')) |
            (InventoryItem.serial_number.ilike(f'%{search_query}%')) |
            (InventoryItem.details.ilike(f'%{search_query}%')) |
            (Person.first_name.ilike(f'%{search_query}%')) |
            (Person.last_name.ilike(f'%{search_query}%'))
        )
    items = query.all()
    return render_template('assets.html', items=items, search_query=search_query, user_role=current_user.role)

@app.route('/person/<int:id>')
@login_required
def person_detail(id):
    person = Person.query.get_or_404(id)
    return render_template('person_detail.html', person=person, user_role=current_user.role)

@app.route('/add-user', methods=['GET', 'POST'])
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'read_only')
        if not all([username, password]):
            flash('Username and password are required.', 'error')
            return redirect(url_for('add_user'))
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return redirect(url_for('add_user'))
        user = User(
            username=username,
            password=generate_password_hash(password),
            role=role
        )
        db.session.add(user)
        db.session.flush()
        log_action('create', 'User', user.id, current_user.id, f'Created user: {username} ({role})')
        db.session.commit()
        flash('User created successfully.', 'success')
        return redirect(url_for('users'))
    return render_template('add_user.html')

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        if not all([current_password, new_password, confirm_password]):
            flash('All fields are required.', 'error')
            return redirect(url_for('change_password'))
        if new_password != confirm_password:
            flash('New password and confirmation do not match.', 'error')
            return redirect(url_for('change_password'))
        if not check_password_hash(current_user.password, current_password):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('change_password'))
        current_user.password = generate_password_hash(new_password)
        db.session.flush()
        log_action('update', 'User', current_user.id, current_user.id, f'Changed password for user: {current_user.username}')
        db.session.commit()
        flash('Password changed successfully.', 'success')
        return redirect(url_for('index'))
    return render_template('change_password.html')

@app.route('/change-user-password/<int:id>', methods=['GET', 'POST'])
@admin_required
def change_user_password(id):
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        if not all([new_password, confirm_password]):
            flash('New password and confirmation are required.', 'error')
            return redirect(url_for('change_user_password', id=id))
        if new_password != confirm_password:
            flash('New password and confirmation do not match.', 'error')
            return redirect(url_for('change_user_password', id=id))
        user.password = generate_password_hash(new_password)
        db.session.flush()
        log_action('update', 'User', user.id, current_user.id, f'Admin {current_user.username} changed password for user: {user.username}')
        db.session.commit()
        flash(f'Password changed successfully for {user.username}.', 'success')
        return redirect(url_for('users'))
    return render_template('change_user_password.html', user=user)

@app.route('/import-csv', methods=['GET', 'POST'])
@admin_required
def import_csv():
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(url_for('import_csv'))
        file = request.files['csv_file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('import_csv'))
        try:
            stream = io.StringIO(file.stream.read().decode('UTF8'), newline=None)
            reader = csv.DictReader(stream)
            required_fields = {'first_name', 'last_name', 'department'}
            if not required_fields.issubset(reader.fieldnames):
                flash('CSV must include columns: first_name, last_name, department (email is optional)', 'error')
                return redirect(url_for('import_csv'))
            
            created_count = 0
            for row in reader:
                if row.get('email') and Person.query.filter_by(email=row.get('email')).first():
                    continue
                person = Person(
                    first_name=row['first_name'],
                    last_name=row['last_name'],
                    email=row.get('email', f"{row['first_name'].lower()}.{row['last_name'].lower()}@company.com"),
                    department=row['department']
                )
                db.session.add(person)
                db.session.flush()
                log_action('create', 'Person', person.id, current_user.id, f'Imported person: {person.first_name} {person.last_name}')
                created_count += 1
            db.session.commit()
            flash(f'Successfully imported {created_count} person(s)', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error importing CSV: {str(e)}', 'error')
    return render_template('import_csv.html')

@app.route('/export-csv')
@admin_required
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['first_name', 'last_name', 'email', 'department'])
    for person in Person.query.all():
        writer.writerow([person.first_name, person.last_name, person.email or '', person.department])
    output.seek(0)
    log_action('export', 'Person', 0, current_user.id, 'Exported all persons to CSV')
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=persons.csv'}
    )

@app.route('/add-item', methods=['GET', 'POST'])
@admin_required
def add_item():
    person_id = request.args.get('person_id')
    pre_assigned_person = Person.query.get(person_id) if person_id else None
    if request.method == 'POST':
        item_type = request.form['item_type'].strip()
        serial_number = request.form['serial_number'].strip()
        details = request.form['details'].strip()
        is_stock = request.form.get('is_stock')
        assigned_to_id = request.form.get('assigned_to') if not is_stock else None
        if not all([item_type, serial_number]):
            flash('Item Type and Serial Number are required.', 'error')
            return redirect(url_for('add_item', person_id=person_id))
        if InventoryItem.query.filter_by(serial_number=serial_number).first():
            flash('Serial number already exists.', 'error')
            return redirect(url_for('add_item', person_id=person_id))
        if not is_stock and not assigned_to_id:
            flash('Assigned To is required unless adding to stock.', 'error')
            return redirect(url_for('add_item', person_id=person_id))
        item = InventoryItem(
            item_type=item_type,
            serial_number=serial_number,
            details=details,
            assigned_to_id=assigned_to_id,
            status='active' if assigned_to_id else 'stock'
        )
        db.session.add(item)
        db.session.flush()
        log_action('create', 'InventoryItem', item.id, current_user.id, f'Added item: {item.item_type} ({item.serial_number})' + (' to stock' if is_stock else ''))
        db.session.commit()
        flash('Item added successfully', 'success')
        if assigned_to_id:
            return redirect(url_for('person_detail', id=assigned_to_id))
        else:
            return redirect(url_for('assets'))
    people = Person.query.all()
    return render_template('add_item.html', people=people, pre_assigned_person=pre_assigned_person)

@app.route('/add-person', methods=['GET', 'POST'])
@admin_required
def add_person():
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        department = request.form.get('department', '').strip()
        if not all([first_name, last_name, email, department]):
            flash('All fields (First Name, Last Name, Email, Department) are required.', 'error')
            return redirect(url_for('add_person'))
        if Person.query.filter_by(email=email).first():
            flash('Email already exists.', 'error')
            return redirect(url_for('add_person'))
        person = Person(
            first_name=first_name,
            last_name=last_name,
            email=email,
            department=department
        )
        db.session.add(person)
        db.session.flush()
        log_action('create', 'Person', person.id, current_user.id, f'Added person: {first_name} {last_name}')
        db.session.commit()
        flash('Employee added successfully.', 'success')
        return redirect(url_for('index'))
    return render_template('add_person.html')

@app.route('/edit-person/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_person(id):
    person = Person.query.get_or_404(id)
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        department = request.form.get('department', '').strip()
        if not all([first_name, last_name, email, department]):
            flash('All fields (First Name, Last Name, Email, Department) are required.', 'error')
            return redirect(url_for('edit_person', id=id))
        if Person.query.filter(Person.email == email, Person.id != id).first():
            flash('Email already exists.', 'error')
            return redirect(url_for('edit_person', id=id))
        person.first_name = first_name
        person.last_name = last_name
        person.email = email
        person.department = department
        db.session.flush()
        log_action('update', 'Person', person.id, current_user.id, f'Updated person: {first_name} {last_name}')
        db.session.commit()
        flash('Employee updated successfully.', 'success')
        return redirect(url_for('index'))
    return render_template('edit_person.html', person=person)

@app.route('/edit-item/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_item(id):
    item = InventoryItem.query.get_or_404(id)
    if request.method == 'POST':
        item_type = request.form['item_type'].strip()
        serial_number = request.form['serial_number'].strip()
        details = request.form['details'].strip()
        is_stock = request.form.get('is_stock')
        assigned_to_id = request.form.get('assigned_to') if not is_stock else None
        if not all([item_type, serial_number]):
            flash('Item Type and Serial Number are required.', 'error')
            return redirect(url_for('edit_item', id=id))
        if InventoryItem.query.filter(InventoryItem.serial_number == serial_number, InventoryItem.id != id).first():
            flash('Serial number already exists', 'error')
            return redirect(url_for('edit_item', id=id))
        if not is_stock and not assigned_to_id:
            flash('Assigned To is required unless setting to stock.', 'error')
            return redirect(url_for('edit_item', id=id))
        item.item_type = item_type
        item.serial_number = serial_number
        item.details = details
        item.assigned_to_id = assigned_to_id
        item.status = 'active' if assigned_to_id else 'stock'
        db.session.flush()
        log_action('update', 'InventoryItem', item.id, current_user.id, f'Updated item: {item_type} ({serial_number})' + (' to stock' if is_stock else ''))
        db.session.commit()
        flash('Item updated successfully', 'success')
        if assigned_to_id:
            return redirect(url_for('person_detail', id=assigned_to_id))
        else:
            return redirect(url_for('assets'))
    people = Person.query.all()
    return render_template('edit_item.html', item=item, people=people)

@app.route('/delete-item/<int:id>', methods=['POST'])
@admin_required
def delete_item(id):
    item = InventoryItem.query.get_or_404(id)
    assigned_to_id = item.assigned_to_id
    log_action('delete', 'InventoryItem', item.id, current_user.id, f'Deleted item: {item.item_type} ({item.serial_number})')
    db.session.delete(item)
    db.session.commit()
    flash('Item deleted successfully', 'success')
    if assigned_to_id:
        return redirect(url_for('person_detail', id=assigned_to_id))
    else:
        return redirect(url_for('assets'))

@app.route('/delete-person/<int:id>', methods=['POST'])
@admin_required
def delete_person(id):
    person = Person.query.get_or_404(id)
    if InventoryItem.query.filter_by(assigned_to_id=id).first():
        flash('Cannot delete employee with assigned items', 'error')
        return redirect(url_for('index'))
    log_action('delete', 'Person', person.id, current_user.id, f'Deleted person: {person.first_name} {person.last_name}')
    db.session.delete(person)
    db.session.commit()
    flash('Employee deleted successfully', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    local_ip = socket.gethostbyname(socket.gethostname())
    print("🚀 Starting Flask application...")
    print("Database should already exist. If not, run 'python create_database.py' first.")
    print("Login: admin / admin123")
    print(f"URL: http://{local_ip}:9000")
    app.run(host='0.0.0.0', port=9000, debug=True)