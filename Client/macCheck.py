import uuid

def get_mac_address():
    """Return the MAC address of the current device as a formatted string."""
    mac = uuid.getnode()
    # Convert to string format: XX:XX:XX:XX:XX:XX
    mac_str = ':'.join(f'{(mac >> i) & 0xff:02X}' for i in range(40, -1, -8))
    print(mac_str)
    return mac_str

# Example usage
get_mac_address()
