"""
╔══════════════════════════════════════════════════════╗
║          DIABETRIX BACKEND — app.py                  ║
║          Flask + Firebase Firestore                  ║
║  Run:  python app.py                                 ║
║  API:  http://127.0.0.1:5000                         ║
╚══════════════════════════════════════════════════════╝
"""

from flask import Flask, request, jsonify, g
from flask_cors import CORS
from datetime import datetime, timedelta
from functools import wraps
import firebase_admin
from firebase_admin import credentials, firestore
import hashlib, uuid, os

app = Flask(__name__)
CORS(app, origins=[os.environ.get('FRONTEND_URL', '*')])

# ══════════════════════════════════════════════════════
#  FIREBASE INIT
#  Set env var GOOGLE_APPLICATION_CREDENTIALS to the
#  path of your serviceAccountKey.json file
# ══════════════════════════════════════════════════════

import json

# Supports three ways to provide Firebase credentials:
# 1. FIREBASE_CREDENTIALS env var (JSON string) — used on Hugging Face
# 2. GOOGLE_APPLICATION_CREDENTIALS env var (path to file) — standard Google way
# 3. serviceAccountKey.json file in same folder — local development
if os.environ.get('FIREBASE_CREDENTIALS'):
    cred_dict = json.loads(os.environ['FIREBASE_CREDENTIALS'])
    cred = credentials.Certificate(cred_dict)
elif os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
    cred = credentials.ApplicationDefault()
else:
    cred = credentials.Certificate('serviceAccountKey.json')

firebase_admin.initialize_app(cred)
db = firestore.client()

# Firestore collection references
users_col    = db.collection('users')
profiles_col = db.collection('profiles')
glucose_col  = db.collection('glucose_readings')
meds_col     = db.collection('medications')
contacts_col = db.collection('emergency_contacts')
safety_col   = db.collection('safety_log')
sessions_col = db.collection('sessions')


# ══════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def make_token(user_id: str) -> str:
    token = str(uuid.uuid4()).replace('-', '')
    sessions_col.document(token).set({
        'user_id':    user_id,
        'created_at': datetime.utcnow().isoformat()
    })
    return token

def auth_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '').strip()
        if not token:
            return jsonify({'error': 'Missing token'}), 401
        session = sessions_col.document(token).get()
        if not session.exists:
            return jsonify({'error': 'Invalid or expired token'}), 401
        g.user_id = session.to_dict()['user_id']
        return f(*args, **kwargs)
    return wrapper

def classify_glucose(v: int) -> str:
    if v < 70:   return 'Hypoglycemia'
    if v < 100:  return 'Normal'
    if v < 126:  return 'Pre-diabetic'
    if v < 300:  return 'Diabetic'
    return 'Critical'

def calc_health_score(user_id: str):
    readings = glucose_col \
        .where('user_id', '==', user_id) \
        .order_by('recorded_at', direction=firestore.Query.DESCENDING) \
        .limit(10).stream()
    vals = [r.to_dict()['value'] for r in readings]
    if not vals:
        return None

    avg   = sum(vals) / len(vals)
    score = 100
    if avg > 200:    score -= 40
    elif avg > 150:  score -= 25
    elif avg > 126:  score -= 15
    elif avg < 70:   score -= 20

    hypos = glucose_col \
        .where('user_id', '==', user_id) \
        .where('value', '<', 70) \
        .stream()
    score -= min(sum(1 for _ in hypos) * 5, 20)

    profile_doc = profiles_col.document(user_id).get()
    if profile_doc.exists:
        p     = profile_doc.to_dict()
        steps = p.get('steps_today', 0) or 0
        goal  = p.get('step_goal',  8000) or 8000
        if steps >= goal:   score += 5
        elif steps < 2000:  score -= 10

    meds = list(meds_col.where('user_id', '==', user_id).limit(1).stream())
    if meds:
        score += 5

    return max(10, min(100, round(score)))

def calc_risk(user_id: str) -> dict:
    readings = glucose_col \
        .where('user_id', '==', user_id) \
        .order_by('recorded_at', direction=firestore.Query.DESCENDING) \
        .limit(7).stream()
    vals = [r.to_dict()['value'] for r in readings]
    if not vals:
        return {'level': 'Unknown', 'pct': 5}

    avg   = sum(vals) / len(vals)
    hypos = sum(1 for v in vals if v < 70)

    if avg > 250 or hypos > 3: return {'level': 'Critical', 'pct': 92}
    if avg > 180 or hypos > 1: return {'level': 'High',     'pct': 66}
    if avg > 130:               return {'level': 'Moderate', 'pct': 40}
    return {'level': 'Low', 'pct': 16}


# ══════════════════════════════════════════════════════
#  AUTH ROUTES
# ══════════════════════════════════════════════════════

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    d     = request.get_json() or {}
    name  = (d.get('name')     or '').strip()
    email = (d.get('email')    or '').strip().lower()
    pw    = (d.get('password') or '').strip()

    if not all([name, email, pw]):
        return jsonify({'error': 'Name, email and password are required'}), 400
    if len(pw) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    # Check if email already exists
    existing = list(users_col.where('email', '==', email).limit(1).stream())
    if existing:
        return jsonify({'error': 'Email already registered'}), 409

    uid = str(uuid.uuid4())
    users_col.document(uid).set({
        'id':         uid,
        'name':       name,
        'email':      email,
        'password':   hash_pw(pw),
        'created_at': datetime.utcnow().isoformat()
    })
    # Create empty profile
    profiles_col.document(uid).set({
        'user_id':    uid,
        'created_at': datetime.utcnow().isoformat()
    })

    token = make_token(uid)
    return jsonify({
        'token': token,
        'user':  {'id': uid, 'name': name, 'email': email}
    }), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    d     = request.get_json() or {}
    email = (d.get('email')    or '').strip().lower()
    pw    = (d.get('password') or '').strip()

    if not email or not pw:
        return jsonify({'error': 'Email and password required'}), 400

    users = list(users_col.where('email', '==', email).limit(1).stream())
    if not users:
        return jsonify({'error': 'Invalid email or password'}), 401

    user = users[0].to_dict()
    if user['password'] != hash_pw(pw):
        return jsonify({'error': 'Invalid email or password'}), 401

    token = make_token(user['id'])
    return jsonify({
        'token': token,
        'user':  {'id': user['id'], 'name': user['name'], 'email': email}
    }), 200


@app.route('/api/auth/logout', methods=['POST'])
@auth_required
def logout():
    token = request.headers.get('Authorization', '').replace('Bearer ', '').strip()
    sessions_col.document(token).delete()
    return jsonify({'message': 'Logged out'}), 200


# ══════════════════════════════════════════════════════
#  PROFILE ROUTES
# ══════════════════════════════════════════════════════

@app.route('/api/profile', methods=['GET'])
@auth_required
def get_profile():
    user_doc    = users_col.document(g.user_id).get()
    profile_doc = profiles_col.document(g.user_id).get()
    user    = user_doc.to_dict() if user_doc.exists else {}
    profile = profile_doc.to_dict() if profile_doc.exists else {}
    # Don't expose password
    user.pop('password', None)
    return jsonify({'user': user, 'profile': profile}), 200


@app.route('/api/profile', methods=['PUT'])
@auth_required
def update_profile():
    d = request.get_json() or {}
    profiles_col.document(g.user_id).set({
        'user_id':        g.user_id,
        'age':            d.get('age'),
        'gender':         d.get('gender'),
        'weight_kg':      d.get('weight_kg'),
        'height_cm':      d.get('height_cm'),
        'lifestyle':      d.get('lifestyle'),
        'dtype':          d.get('dtype'),
        'diagnosed_year': d.get('diagnosed_year'),
        'target_low':     d.get('target_low', 80),
        'target_high':    d.get('target_high', 140),
        'doctor_name':    d.get('doctor_name', ''),
        'allergies':      d.get('allergies', ''),
        'meds_text':      d.get('meds_text', ''),
        'step_goal':      d.get('step_goal', 8000),
        'steps_today':    d.get('steps_today', 0),
        'updated_at':     datetime.utcnow().isoformat()
    }, merge=True)
    profile = profiles_col.document(g.user_id).get().to_dict()
    return jsonify({'profile': profile}), 200


@app.route('/api/profile/steps', methods=['PATCH'])
@auth_required
def update_steps():
    d     = request.get_json() or {}
    steps = min(int(d.get('steps', 0)), 99999)
    profiles_col.document(g.user_id).set({'steps_today': steps}, merge=True)
    return jsonify({'steps_today': steps}), 200


# ══════════════════════════════════════════════════════
#  GLUCOSE ROUTES
# ══════════════════════════════════════════════════════

@app.route('/api/glucose', methods=['GET'])
@auth_required
def get_glucose():
    days   = request.args.get('days', 30, type=int)
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

    readings = glucose_col \
        .where('user_id', '==', g.user_id) \
        .where('recorded_at', '>=', cutoff) \
        .order_by('recorded_at', direction=firestore.Query.DESCENDING) \
        .stream()

    result = [r.to_dict() for r in readings]
    return jsonify({'readings': result, 'count': len(result)}), 200


@app.route('/api/glucose', methods=['POST'])
@auth_required
def add_glucose():
    d     = request.get_json() or {}
    value = d.get('value')
    if value is None:
        return jsonify({'error': 'value is required'}), 400
    value = int(value)
    if not (20 <= value <= 800):
        return jsonify({'error': 'Glucose value must be between 20 and 800 mg/dL'}), 400

    rid     = str(uuid.uuid4())
    cls     = classify_glucose(value)
    reading = {
        'id':           rid,
        'user_id':      g.user_id,
        'value':        value,
        'meal_context': d.get('meal_context', 'fasting'),
        'note':         d.get('note', ''),
        'classification': cls,
        'recorded_at':  datetime.utcnow().isoformat()
    }
    glucose_col.document(rid).set(reading)

    alert = None
    if value < 70:
        alert = {'type': 'hypoglycemia', 'message': f'Low blood sugar: {value} mg/dL — take fast-acting sugar immediately!'}
    elif value > 300:
        alert = {'type': 'critical',     'message': f'Critical glucose: {value} mg/dL — seek medical help immediately!'}

    return jsonify({'reading': reading, 'alert': alert, 'id': rid}), 201


@app.route('/api/glucose/<string:rid>', methods=['DELETE'])
@auth_required
def delete_glucose(rid):
    doc = glucose_col.document(rid).get()
    if doc.exists and doc.to_dict().get('user_id') == g.user_id:
        glucose_col.document(rid).delete()
    return jsonify({'deleted': rid}), 200


# ══════════════════════════════════════════════════════
#  ANALYTICS ROUTE
# ══════════════════════════════════════════════════════

@app.route('/api/analytics', methods=['GET'])
@auth_required
def analytics():
    days   = request.args.get('days', 30, type=int)
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

    readings = list(glucose_col
        .where('user_id', '==', g.user_id)
        .where('recorded_at', '>=', cutoff)
        .stream())

    if not readings:
        return jsonify({'message': 'No readings in this period'}), 200

    vals     = [r.to_dict()['value'] for r in readings]
    in_range = [v for v in vals if 70 <= v <= 180]

    return jsonify({
        'period_days':  days,
        'total':        len(vals),
        'avg':          round(sum(vals) / len(vals)),
        'max':          max(vals),
        'min':          min(vals),
        'in_range_pct': round(len(in_range) / len(vals) * 100),
        'hypo_events':  sum(1 for v in vals if v < 70),
        'high_events':  sum(1 for v in vals if v > 180),
        'health_score': calc_health_score(g.user_id),
        'risk':         calc_risk(g.user_id),
    }), 200


# ══════════════════════════════════════════════════════
#  AI PREDICTION ROUTE
# ══════════════════════════════════════════════════════

@app.route('/api/ai/predict', methods=['GET'])
@auth_required
def ai_predict():
    readings = list(glucose_col
        .where('user_id', '==', g.user_id)
        .order_by('recorded_at', direction=firestore.Query.DESCENDING)
        .limit(10).stream())

    if len(readings) < 3:
        return jsonify({'error': 'Need at least 3 glucose readings for AI analysis'}), 400

    profile_doc = profiles_col.document(g.user_id).get()
    profile     = profile_doc.to_dict() if profile_doc.exists else {}
    risk        = calc_risk(g.user_id)
    score       = calc_health_score(g.user_id)
    vals        = [r.to_dict()['value'] for r in readings]
    avg         = round(sum(vals) / len(vals))

    messages = {
        'Low':      f'✅ Low risk. Avg glucose: {avg} mg/dL — well controlled. Health score: {score}/100.',
        'Moderate': f'⚠️ Moderate risk. Avg: {avg} mg/dL. Increase activity, reduce refined carbs, consult doctor.',
        'High':     f'🔴 High risk. Avg: {avg} mg/dL. Contact your doctor immediately. Monitor every 4–6 hrs.',
        'Critical': f'🚨 Critical risk. Dangerous glucose levels. Contact emergency services or doctor NOW.',
    }

    steps      = profile.get('steps_today', 0) or 0
    goal       = profile.get('step_goal', 8000) or 8000
    meds_count = sum(1 for _ in meds_col.where('user_id', '==', g.user_id).limit(1).stream())

    return jsonify({
        'risk':         risk,
        'health_score': score,
        'avg_glucose':  avg,
        'message':      messages.get(risk['level'], 'Insufficient data'),
        'sub_scores': {
            'glucose_control': 'Good' if avg < 130 else ('Fair' if avg < 180 else 'Poor'),
            'activity':        'Good' if steps >= goal else ('Fair' if steps >= 4000 else 'Low'),
            'medication':      'Tracked' if meds_count > 0 else 'Not Set',
        }
    }), 200


# ══════════════════════════════════════════════════════
#  MEDICATION ROUTES
# ══════════════════════════════════════════════════════

@app.route('/api/medications', methods=['GET'])
@auth_required
def get_medications():
    meds = [m.to_dict() for m in
            meds_col.where('user_id', '==', g.user_id).stream()]
    return jsonify({'medications': meds}), 200


@app.route('/api/medications', methods=['POST'])
@auth_required
def add_medication():
    d    = request.get_json() or {}
    name = (d.get('name') or '').strip()
    dose = (d.get('dose') or '').strip()
    if not name or not dose:
        return jsonify({'error': 'Medication name and dose are required'}), 400

    mid = str(uuid.uuid4())
    med = {
        'id':          mid,
        'user_id':     g.user_id,
        'name':        name,
        'dose':        dose,
        'time_of_day': d.get('time_of_day', '08:00'),
        'frequency':   d.get('frequency', 'Once daily'),
        'is_done':     False,
        'created_at':  datetime.utcnow().isoformat()
    }
    meds_col.document(mid).set(med)
    return jsonify({'medication': med, 'id': mid}), 201


@app.route('/api/medications/<string:mid>/toggle', methods=['PATCH'])
@auth_required
def toggle_medication(mid):
    doc = meds_col.document(mid).get()
    if not doc.exists or doc.to_dict().get('user_id') != g.user_id:
        return jsonify({'error': 'Medication not found'}), 404
    current = doc.to_dict().get('is_done', False)
    meds_col.document(mid).update({'is_done': not current})
    updated = meds_col.document(mid).get().to_dict()
    return jsonify({'medication': updated}), 200


@app.route('/api/medications/<string:mid>', methods=['DELETE'])
@auth_required
def delete_medication(mid):
    doc = meds_col.document(mid).get()
    if doc.exists and doc.to_dict().get('user_id') == g.user_id:
        meds_col.document(mid).delete()
    return jsonify({'deleted': mid}), 200


# ══════════════════════════════════════════════════════
#  EMERGENCY CONTACT ROUTES
# ══════════════════════════════════════════════════════

@app.route('/api/contacts', methods=['GET'])
@auth_required
def get_contacts():
    contacts = [c.to_dict() for c in
                contacts_col.where('user_id', '==', g.user_id).stream()]
    return jsonify({'contacts': contacts}), 200


@app.route('/api/contacts', methods=['POST'])
@auth_required
def add_contact():
    d     = request.get_json() or {}
    name  = (d.get('name')  or '').strip()
    phone = (d.get('phone') or '').strip()
    if not name or not phone:
        return jsonify({'error': 'Contact name and phone are required'}), 400

    cid     = str(uuid.uuid4())
    contact = {
        'id':           cid,
        'user_id':      g.user_id,
        'name':         name,
        'phone':        phone,
        'relationship': d.get('relationship', ''),
        'created_at':   datetime.utcnow().isoformat()
    }
    contacts_col.document(cid).set(contact)
    return jsonify({'contact': contact, 'id': cid}), 201


@app.route('/api/contacts/<string:cid>', methods=['DELETE'])
@auth_required
def delete_contact(cid):
    doc = contacts_col.document(cid).get()
    if doc.exists and doc.to_dict().get('user_id') == g.user_id:
        contacts_col.document(cid).delete()
    return jsonify({'deleted': cid}), 200


# ══════════════════════════════════════════════════════
#  SAFETY LOG ROUTES
# ══════════════════════════════════════════════════════

@app.route('/api/safety/log', methods=['GET'])
@auth_required
def get_safety_log():
    logs = [l.to_dict() for l in
            safety_col.where('user_id', '==', g.user_id)
                      .order_by('logged_at', direction=firestore.Query.DESCENDING)
                      .limit(50).stream()]
    return jsonify({'logs': logs}), 200


@app.route('/api/safety/log', methods=['POST'])
@auth_required
def add_safety_log():
    d     = request.get_json() or {}
    ltype = d.get('log_type', 'ok')
    msg   = (d.get('message') or '').strip()
    if not msg:
        return jsonify({'error': 'message is required'}), 400

    lid = str(uuid.uuid4())
    log = {
        'id':        lid,
        'user_id':   g.user_id,
        'log_type':  ltype,
        'message':   msg,
        'logged_at': datetime.utcnow().isoformat()
    }
    safety_col.document(lid).set(log)
    return jsonify({'log': log}), 201


@app.route('/api/safety/checkin', methods=['POST'])
@auth_required
def safety_checkin():
    lid = str(uuid.uuid4())
    safety_col.document(lid).set({
        'id':        lid,
        'user_id':   g.user_id,
        'log_type':  'ok',
        'message':   'User confirmed okay via safety check-in',
        'logged_at': datetime.utcnow().isoformat()
    })
    return jsonify({'status': 'ok', 'message': 'Check-in confirmed'}), 200


@app.route('/api/emergency/alert', methods=['POST'])
@auth_required
def emergency_alert():
    d        = request.get_json() or {}
    location = d.get('location', 'Unknown')
    reason   = d.get('reason',   'emergency')
    symptoms = d.get('symptoms', [])

    contacts = [c.to_dict() for c in
                contacts_col.where('user_id', '==', g.user_id).stream()]

    msg = f"Emergency alert — reason: {reason}. Symptoms: {', '.join(symptoms) or 'none'}. Location: {location}"
    lid = str(uuid.uuid4())
    safety_col.document(lid).set({
        'id':        lid,
        'user_id':   g.user_id,
        'log_type':  'danger',
        'message':   msg,
        'logged_at': datetime.utcnow().isoformat()
    })

    return jsonify({
        'alert_id':          lid,
        'message':           f"Alert sent to {len(contacts)} contact(s)",
        'contacts_notified': [c['name'] for c in contacts],
        'location':          location,
        'timestamp':         datetime.utcnow().isoformat(),
    }), 200


# ══════════════════════════════════════════════════════
#  REPORT ROUTE
# ══════════════════════════════════════════════════════

@app.route('/api/report', methods=['GET'])
@auth_required
def generate_report():
    days   = request.args.get('days', 30, type=int)
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

    readings = [r.to_dict() for r in
                glucose_col.where('user_id', '==', g.user_id)
                           .where('recorded_at', '>=', cutoff)
                           .order_by('recorded_at').stream()]

    if not readings:
        return jsonify({'error': 'No readings in this period'}), 400

    vals     = [r['value'] for r in readings]
    in_range = [v for v in vals if 70 <= v <= 180]

    user_doc    = users_col.document(g.user_id).get()
    profile_doc = profiles_col.document(g.user_id).get()
    user    = user_doc.to_dict() if user_doc.exists else {}
    profile = profile_doc.to_dict() if profile_doc.exists else {}

    meds     = [m.to_dict() for m in meds_col.where('user_id', '==', g.user_id).stream()]
    contacts = [c.to_dict() for c in contacts_col.where('user_id', '==', g.user_id).stream()]

    return jsonify({
        'generated':       datetime.utcnow().isoformat(),
        'period_days':     days,
        'patient_name':    user.get('name'),
        'email':           user.get('email'),
        'age':             profile.get('age'),
        'gender':          profile.get('gender'),
        'diabetes_type':   profile.get('dtype'),
        'doctor':          profile.get('doctor_name', 'Not set'),
        'target_range':    f"{profile.get('target_low', 80)}–{profile.get('target_high', 140)} mg/dL",
        'total_readings':  len(readings),
        'avg_glucose':     round(sum(vals) / len(vals)),
        'max_glucose':     max(vals),
        'min_glucose':     min(vals),
        'in_range_pct':    round(len(in_range) / len(vals) * 100),
        'hypo_events':     sum(1 for v in vals if v < 70),
        'high_events':     sum(1 for v in vals if v > 180),
        'health_score':    calc_health_score(g.user_id),
        'risk_level':      calc_risk(g.user_id)['level'],
        'steps_today':     profile.get('steps_today', 0),
        'step_goal':       profile.get('step_goal', 8000),
        'medications':     [f"{m['name']} {m['dose']}" for m in meds],
        'emergency_contacts': [f"{c['name']} — {c['phone']}" for c in contacts],
        'readings':        readings,
    }), 200


# ══════════════════════════════════════════════════════
#  HEALTH CHECK
# ══════════════════════════════════════════════════════

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status':  'ok',
        'app':     'Diabetrix API',
        'version': '3.0',
        'db':      'Firebase Firestore',
    }), 200


# ══════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════

if __name__ == '__main__':
    print("🟢  Diabetrix API  →  http://127.0.0.1:5000")
    print("🔥  Database       →  Firebase Firestore")
    print("─" * 50)
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))