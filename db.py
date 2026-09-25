import os
import json
import logging
from datetime import datetime
import pytz
import firebase_admin
from firebase_admin import credentials, db

FIREBASE_CREDENTIALS = os.environ.get("FIREBASE_CREDENTIALS")
FIREBASE_DB_URL = os.environ.get("FIREBASE_DB_URL")

db_ref = None

if FIREBASE_CREDENTIALS and FIREBASE_DB_URL:
    try:
        cert_dict = json.loads(FIREBASE_CREDENTIALS)
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred, {
            'databaseURL': FIREBASE_DB_URL
        })
        db_ref = db.reference()
        logging.info("✅ ភ្ជាប់ទៅកាន់ Firebase បានជោគជ័យ!")
    except Exception as e:
        logging.error(f"❌ បរាជ័យក្នុងការភ្ជាប់ Firebase: {e}")
else:
    logging.warning("⚠️ មិនបានដាក់ FIREBASE_CREDENTIALS ឬ FIREBASE_DB_URL ទេ ប្រព័ន្ធកាក់នឹងមិនដំណើរការឡើយ។")

def get_today_str():
    # ប្រើម៉ោងនៅកម្ពុជា
    tz = pytz.timezone('Asia/Phnom_Penh')
    return datetime.now(tz).strftime('%Y-%m-%d')

def get_user_balance(user_id):
    if not db_ref: return {'free': 5, 'paid': 0} 
    
    user_id = str(user_id)
    user_data = db_ref.child('users').child(user_id).get()
    today = get_today_str()
    
    if not user_data:
        user_data = {
            'free_coins': 5,
            'paid_coins': 0,
            'last_free_date': today
        }
        db_ref.child('users').child(user_id).set(user_data)
        return {'free': 5, 'paid': 0}
        
    # ប្រសិនបើចូលថ្ងៃថ្មី ផ្តល់ ៥ កាក់ Free វិញ
    if user_data.get('last_free_date') != today:
        user_data['free_coins'] = 5
        user_data['last_free_date'] = today
        db_ref.child('users').child(user_id).update({
            'free_coins': 5,
            'last_free_date': today
        })
        
    return {'free': user_data.get('free_coins', 0), 'paid': user_data.get('paid_coins', 0)}

def deduct_coins(user_id, amount):
    if not db_ref: return True
    
    user_id = str(user_id)
    balance = get_user_balance(user_id)
    
    total = balance['free'] + balance['paid']
    if total < amount:
        return False
        
    free = balance['free']
    paid = balance['paid']
    
    # កាត់កាក់ Free មុន
    if free >= amount:
        free -= amount
    else:
        amount -= free
        free = 0
        paid -= amount
        
    db_ref.child('users').child(user_id).update({
        'free_coins': free,
        'paid_coins': paid
    })
    return True

def add_paid_coins(user_id, amount):
    if not db_ref: return False
    
    user_id = str(user_id)
    balance = get_user_balance(user_id)
    new_paid = balance['paid'] + amount
    db_ref.child('users').child(user_id).update({
        'paid_coins': new_paid
    })
    return True

def check_receipt(receipt_id):
    if not db_ref: return False
    data = db_ref.child('receipts').child(receipt_id).get()
    return bool(data)

def save_receipt(receipt_id, user_id):
    if not db_ref: return
    db_ref.child('receipts').child(receipt_id).set({
        'user_id': str(user_id),
        'timestamp': get_today_str()
    })
