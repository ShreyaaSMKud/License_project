import uuid
import requests
import json
import os

# ==== CONFIGURATION ====
SERVER_IP = '192.168.1.4'
PORT = 443  # ⬅️ Replace with your actual server IP
CERT_PATH = 'cert.pem'       # ⬅️ This is the server's self-signed certificate
LICENSE_FILE = 'license.json'

REQUEST_LICENSE_URL = f'https://{SERVER_IP}:{PORT}/request-license'
VALIDATE_LICENSE_URL = f'https://{SERVER_IP}:{PORT}/validate-license'

# ==== FUNCTIONS ====

def get_mac_address():
    """Return the MAC address of the current device as a colon-separated string."""
    mac = uuid.getnode()
    return ':'.join(f'{(mac >> i) & 0xff:02x}' for i in range(40, -1, -8))

def normalize_mac(mac):
    """Convert MAC to uppercase with dashes (e.g., AA-BB-CC-DD-EE-FF)."""
    return mac.upper().replace(":", "-")

def save_license(short_key, expiry_date):
    """Save license locally to a file."""
    with open(LICENSE_FILE, 'w') as f:
        json.dump({'license_key': short_key, 'expiry_date': expiry_date}, f)

def load_license():
    """Load license from local file."""
    if not os.path.exists(LICENSE_FILE):
        return None
    with open(LICENSE_FILE, 'r') as f:
        return json.load(f)

def request_new_license():
    """Request a new license from the server."""
    mac = normalize_mac(get_mac_address())
    print(f"➡️ Sending MAC address to server: {mac}")
    payload = {
        'mac_address': mac,
        'duration_days': 30,
        'max_activations': 3
    }
    try:
        response = requests.post(REQUEST_LICENSE_URL, json=payload, verify=CERT_PATH)
        if response.status_code == 200:
            data = response.json()
            print("✅ License issued:", data)
            save_license(data['license_key'], data['expiry_date'])
        else:
            print("❌ Failed to get license:", response.status_code, response.json())
    except Exception as e:
        print("❌ Error during license request:", e)

def validate_license():
    """Validate the existing license with the server."""
    mac = normalize_mac(get_mac_address())
    license_data = load_license()
    if not license_data:
        print("❌ No license found. Please request one first.")
        return
    payload = {
        'license_key': license_data['license_key'],
        'mac_address': mac
    }
    try:
        response = requests.post(VALIDATE_LICENSE_URL, json=payload, verify=CERT_PATH)
        if response.status_code == 200:
            data = response.json()
            if data.get('valid'):
                print("✅ License is valid:", data['license_data'])
            else:
                print("❌ License invalid:", data['reason'])
        else:
            print("❌ Validation error:", response.status_code, response.json())
    except Exception as e:
        print("❌ Error during license validation:", e)

# ==== MAIN MENU ====
def main():
    while True:
        print("\nLicense Client Menu:")
        print("1. Request new license")
        print("2. Validate existing license")
        print("3. Exit")
        choice = input("Choose an option (1-3): ")
        if choice == '1':
            request_new_license()
        elif choice == '2':
            validate_license()
        elif choice == '3':
            break
        else:
            print("Invalid choice. Try again.")

if __name__ == "__main__":
    main()
