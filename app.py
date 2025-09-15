from flask import Flask, render_template, request, redirect, url_for, flash, send_file, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import csv
import io
from models import db, Person, InventoryItem, User
import os

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    people = Person.query.all()
    total_items = InventoryItem.query.count()
    return render_template('index.html', people=people, total_items=total_items)

@app.route('/person/<int:id>')
@login_required
def person_detail(id):
    person = Person.query.get_or_404(id)
    items = InventoryItem.query.filter_by(assigned_to_id=id).all()
    return render_template('person_detail.html', person=person, items=items)

@app.route('/import-csv', methods=['GET', 'POST'])
@login_required
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
                if Person.query.filter_by(email=row.get('email', '')).first():
                    continue  # Skip if email already exists (unique constraint)
                person = Person(
                    first_name=row['first_name'],
                    last_name=row['last_name'],
                    email=row.get('email', None),
                    department=row['department']
                )
                db.session.add(person)
                created_count += 1
            db.session.commit()
            flash(f'Successfully imported {created_count} person(s)', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error importing CSV: {str(e)}', 'error')
    return render_template('import_csv.html')

@app.route('/export-csv')
@login_required
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['first_name', 'last_name', 'email', 'department'])
    for person in Person.query.all():
        writer.writerow([person.first_name, person.last_name, person.email or '', person.department])
    output.seek(0)
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=persons.csv'}
    )

@app.route('/add-item', methods=['GET', 'POST'])
@login_required
def add_item():
    if request.method == 'POST':
        item_type = request.form['item_type']
        serial_number = request.form['serial_number']
        details = request.form['details']
        assigned_to_id = request.form['assigned_to']
        item = InventoryItem(
            item_type=item_type,
            serial_number=serial_number,
            details=details,
            assigned_to_id=assigned_to_id,
            status='active'
        )
        db.session.add(item)
        db.session.commit()
        flash('Item added successfully', 'success')
        return redirect(url_for('person_detail', id=assigned_to_id))
    people = Person.query.all()
    return render_template('add_item.html', people=people)

@app.route('/add-person', methods=['GET', 'POST'])
@login_required
def add_person():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        department = request.form.get('department', '').strip()

        if not all([full_name, email, department]):
            flash('All fields (Full Name, Email, Department) are required.', 'error')
            return redirect(url_for('add_person'))
        
        # Split full name into first_name and last_name
        name_parts = full_name.split(maxsplit=1)
        if len(name_parts) < 2:
            flash('Full Name must include both first and last name.', 'error')
            return redirect(url_for('add_person'))
        first_name, last_name = name_parts[0], name_parts[1]

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
        db.session.commit()
        flash('Employee added successfully.', 'success')
        return redirect(url_for('index'))
    return render_template('add_person.html')

@app.route('/edit-person/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_person(id):
    person = Person.query.get_or_404(id)
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        department = request.form.get('department', '').strip()
        if not all([full_name, email, department]):
            flash('All fields (Full Name, Email, Department) are required.', 'error')
            return redirect(url_for('edit_person', id=id))
        
        name_parts = full_name.split(maxsplit=1)
        if len(name_parts) < 2:
            flash('Full Name must include both first and last name.', 'error')
            return redirect(url_for('edit_person', id=id))
        first_name, last_name = name_parts[0], name_parts[1]

        if Person.query.filter_by(email=email).filter(Person.id != id).first():
            flash('Email already exists.', 'error')
            return redirect(url_for('edit_person', id=id))
        
        person.first_name = first_name
        person.last_name = last_name
        person.email = email
        person.department = department
        db.session.commit()
        flash('Employee updated successfully.', 'success')
        return redirect(url_for('index'))
    return render_template('edit_person.html', person=person)

@app.route('/edit-item/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_item(id):
    item = InventoryItem.query.get_or_404(id)
    if request.method == 'POST':
        item_type = request.form['item_type']
        serial_number = request.form['serial_number']
        details = request.form['details']
        assigned_to_id = request.form['assigned_to']
        if InventoryItem.query.filter_by(serial_number=serial_number).filter(InventoryItem.id != id).first():
            flash('Serial number already exists', 'error')
            return redirect(url_for('edit_item', id=id))
        item.item_type = item_type
        item.serial_number = serial_number
        item.details = details
        item.assigned_to_id = assigned_to_id
        db.session.commit()
        flash('Item updated successfully', 'success')
        return redirect(url_for('person_detail', id=assigned_to_id))
    people = Person.query.all()
    return render_template('edit_item.html', item=item, people=people)

@app.route('/delete-item/<int:id>', methods=['POST'])
@login_required
def delete_item(id):
    item = InventoryItem.query.get_or_404(id)
    assigned_to_id = item.assigned_to_id
    db.session.delete(item)
    db.session.commit()
    flash('Item deleted successfully', 'success')
    return redirect(url_for('person_detail', id=assigned_to_id))

@app.route('/delete-person/<int:id>', methods=['POST'])
@login_required
def delete_person(id):
    person = Person.query.get_or_404(id)
    if InventoryItem.query.filter_by(assigned_to_id=id).first():
        flash('Cannot delete employee with assigned items', 'error')
        return redirect(url_for('index'))
    db.session.delete(person)
    db.session.commit()
    flash('Employee deleted successfully', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    print("🚀 Starting Flask application...")
    print("Database should already exist. If not, run 'python fix_database.py' first.")
    print("Login: admin / admin123")
    print("URL: http://192.168.10.199:9000")
    app.run(host='192.168.10.199', port=9000, debug=True)