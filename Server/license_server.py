from flask import Flask, request, jsonify
import sqlite3
import jwt
import secrets
import hmac
import hashlib
from datetime import datetime, timedelta

app = Flask(__name__)

DB_FILE = 'licenses.db'

# Load RSA keys
with open("private_key.pem", "rb") as f:
    PRIVATE_KEY = f.read()

with open("public_key.pem", "rb") as f:
    PUBLIC_KEY = f.read()

JWT_ALGORITHM = 'RS256'

SHORT_KEY_LENGTH = 12  # Length of short key (characters)

def generate_short_key(jwt_token):
    """
    Derive a short key from the JWT token using HMAC-SHA256 with a secret.
    This links the short key cryptographically to the JWT.
    Returns a human-readable base32-encoded string.
    """
    # For HMAC secret, use first 32 bytes of public key (or generate a secret)
    secret = PUBLIC_KEY[:32]

    digest = hmac.new(secret, jwt_token.encode(), hashlib.sha256).digest()
    short_key = secrets.base64.b32encode(digest).decode('utf-8').rstrip('=')
    short_key = short_key[:SHORT_KEY_LENGTH]
    parts = [short_key[i:i+4] for i in range(0, SHORT_KEY_LENGTH, 4)]
    return '-'.join(parts)

def is_short_key_unique(short_key):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT 1 FROM licenses WHERE short_key = ?', (short_key,))
    exists = c.fetchone() is not None
    conn.close()
    return not exists

def normalize_mac(mac):
    """Normalize MAC to uppercase with dashes."""
    mac = mac.upper().replace(":", "-")
    return mac

def is_mac_approved(mac_address):
    normalized_mac = normalize_mac(mac_address)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT 1 FROM valid_macs WHERE mac_address = ?', (normalized_mac,))
    exists = c.fetchone() is not None
    conn.close()
    return exists


def create_jwt_license(mac, expiry_date, max_activations):
    payload = {
        'mac_address': mac,
        'expiry_date': expiry_date,
        'max_activations': max_activations,
        'iat': datetime.utcnow().timestamp()
    }
    token = jwt.encode(payload, PRIVATE_KEY, algorithm=JWT_ALGORITHM)
    return token

def save_license(mac_address, short_key, jwt_token, expiry_date, max_activations):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('SELECT short_key FROM licenses WHERE mac_address = ?', (mac_address,))
    existing = c.fetchone()

    if existing:
        c.execute('''
            UPDATE licenses
            SET short_key = ?, jwt_token = ?, expiry_date = ?, max_activations = ?, activations = 0, revoked = 0
            WHERE mac_address = ?
        ''', (short_key, jwt_token, expiry_date, max_activations, mac_address))
    else:
        c.execute('''
            INSERT INTO licenses (mac_address, short_key, jwt_token, expiry_date, max_activations, activations, revoked)
            VALUES (?, ?, ?, ?, ?, 0, 0)
        ''', (mac_address, short_key, jwt_token, expiry_date, max_activations))

    conn.commit()
    conn.close()

def log_activation(mac_address, short_key, success, reason=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO activations_log (mac_address, short_key, success, reason)
        VALUES (?, ?, ?, ?)
    ''', (mac_address, short_key, int(success), reason))
    conn.commit()
    conn.close()

@app.route('/request-license', methods=['POST'])
def request_license():
    data = request.json
    mac_address = normalize_mac(data.get('mac_address', ''))
    if not mac_address:
        return jsonify({'error': 'MAC address is required'}), 400

    # Check if MAC is approved
    if not is_mac_approved(mac_address):
        return jsonify({'error': 'MAC address not authorized for license'}), 403

    # ✅ Check if license already exists
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT short_key FROM licenses WHERE mac_address = ?', (mac_address,))
    existing_license = c.fetchone()
    conn.close()
    if existing_license:
        return jsonify({'error': 'License already exists for this MAC address'}), 409

    # Create new license
    duration_days = data.get('duration_days', 30)
    max_activations = data.get('max_activations', 3)
    expiry_date = (datetime.utcnow() + timedelta(days=duration_days)).strftime('%Y-%m-%d')
    jwt_token = create_jwt_license(mac_address, expiry_date, max_activations)

    # Generate unique short key
    short_key = generate_short_key(jwt_token)
    attempts = 0
    while not is_short_key_unique(short_key) and attempts < 5:
        jwt_token_with_nonce = jwt_token + secrets.token_urlsafe(4)
        short_key = generate_short_key(jwt_token_with_nonce)
        attempts += 1
    if attempts == 5:
        return jsonify({'error': 'Could not generate unique license key, try again'}), 500

    # Save license
    save_license(mac_address, short_key, jwt_token, expiry_date, max_activations)

    return jsonify({
        'mac_address': mac_address,
        'license_key': short_key,
        'expiry_date': expiry_date
    }), 200
@app.route('/validate-license', methods=['POST'])
def validate_license():
    data = request.json
    short_key = data.get('license_key')
    mac_address = data.get('mac_address')
    if not short_key or not mac_address:
        return jsonify({'valid': False, 'reason': 'License key and MAC address are required'}), 400

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT jwt_token, activations, max_activations, revoked FROM licenses WHERE short_key = ?', (short_key,))
    row = c.fetchone()
    conn.close()

    if not row:
        log_activation(mac_address, short_key, False, 'License key not found')
        return jsonify({'valid': False, 'reason': 'License key not found'}), 400

    jwt_token, activations, max_activations, revoked = row

    if revoked:
        log_activation(mac_address, short_key, False, 'License revoked')
        return jsonify({'valid': False, 'reason': 'License has been revoked'}), 200

    if activations >= max_activations:
        log_activation(mac_address, short_key, False, 'Activation limit exceeded')
        return jsonify({'valid': False, 'reason': 'Activation limit exceeded'}), 200

    try:
        license_data = jwt.decode(jwt_token, PUBLIC_KEY, algorithms=[JWT_ALGORITHM])

        if license_data.get('mac_address') != mac_address:
            log_activation(mac_address, short_key, False, 'MAC address mismatch')
            return jsonify({'valid': False, 'reason': 'MAC address does not match license'}), 400

        expiry_date = datetime.strptime(license_data['expiry_date'], '%Y-%m-%d')
        if datetime.utcnow() > expiry_date:
            log_activation(mac_address, short_key, False, 'License expired')
            return jsonify({'valid': False, 'reason': 'License expired'}), 200

        expected_short_key = generate_short_key(jwt_token)
        if expected_short_key != short_key:
            log_activation(mac_address, short_key, False, 'Short key mismatch')
            return jsonify({'valid': False, 'reason': 'License key does not match license data'}), 400

    except jwt.ExpiredSignatureError:
        log_activation(mac_address, short_key, False, 'License expired (JWT)')
        return jsonify({'valid': False, 'reason': 'License expired'}), 200
    except jwt.InvalidTokenError:
        log_activation(mac_address, short_key, False, 'Invalid license token')
        return jsonify({'valid': False, 'reason': 'Invalid license token'}), 400

    # Update activation count
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE licenses SET activations = activations + 1 WHERE short_key = ?', (short_key,))
    conn.commit()
    conn.close()

    log_activation(mac_address, short_key, True)

    return jsonify({'valid': True, 'license_data': license_data}), 200

@app.route('/revoke-license', methods=['POST'])
def revoke_license():
    data = request.json
    short_key = data.get('license_key')
    if not short_key:
        return jsonify({'success': False, 'message': 'License key required'}), 400

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE licenses SET revoked = 1 WHERE short_key = ?', (short_key,))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'License revoked successfully'}), 200

if __name__ == '__main__':
    context = ('cert.pem', 'key.pem')  # Paths to your self-signed cert and key files
    app.run(debug=True, ssl_context=context, host='0.0.0.0', port=443)
