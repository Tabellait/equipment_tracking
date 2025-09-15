#!/usr/bin/env python3
"""
Quick fix script to resolve the database schema issue.
"""

import os
import shutil
from flask import Flask
from werkzeug.security import generate_password_hash

def cleanup():
    """Remove problematic files"""
    print("🧹 Cleaning up...")
    
    # Remove database files
    db_files = ['db.sqlite3', 'instance/db.sqlite3']
    for db_file in db_files:
        if os.path.exists(db_file):
            os.remove(db_file)
            print(f"  ✓ Removed {db_file}")
    
    # Remove Python cache
    if os.path.exists('__pycache__'):
        shutil.rmtree('__pycache__')
        print("  ✓ Removed __pycache__")

def create_database():
    """Create fresh database"""
    print("\n📂 Creating fresh database...")
    
    # Import models
    from models import db, Person, InventoryItem, User
    
    # Create Flask app
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'your-secret-key-replace-this'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    
    with app.app_context():
        # Create tables
        db.create_all()
        print("  ✓ Tables created")
        
        # Add admin user
        admin = User(username='admin', password=generate_password_hash('admin123'))
        db.session.add(admin)
        
        # Add sample people
        people = [
            Person(first_name='John', last_name='Doe', email='john.doe@company.com', department='IT'),
            Person(first_name='Jane', last_name='Smith', email='jane.smith@company.com', department='HR'),
            Person(first_name='Bob', last_name='Johnson', email='bob.johnson@company.com', department='Finance')
        ]
        
        for person in people:
            db.session.add(person)
        
        # Add sample items
        items = [
            InventoryItem(item_type='Laptop', serial_number='LT001', details='Dell Latitude', assigned_to_id=1, status='active'),
            InventoryItem(item_type='Mouse', serial_number='MS001', details='Wireless Mouse', assigned_to_id=1, status='active'),
        ]
        
        for item in items:
            db.session.add(item)
        
        db.session.commit()
        print("  ✓ Sample data added")
        
        # Verify
        print(f"  ✓ People: {Person.query.count()}")
        print(f"  ✓ Items: {InventoryItem.query.count()}")
        print(f"  ✓ Users: {User.query.count()}")

def main():
    print("🔧 Database Fix Script")
    print("=" * 30)
    
    try:
        cleanup()
        create_database()
        print("\n✅ Database fixed successfully!")
        print("\nLogin credentials:")
        print("  Username: admin")
        print("  Password: admin123")
        print("\nRun: python app.py")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()