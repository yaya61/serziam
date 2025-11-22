#!/usr/bin/env python3
"""
GÉNÉRATEUR SIMPLIFIÉ DE CODE ASTERISK
Version minimaliste - Même algorithme
"""

import hashlib
import hmac
from datetime import datetime

# CONFIGURATION IDENTIQUE
SECRET_SEED = "asterisk_secure_deterministic_v1"
MONTH_NAMES = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août", 
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}

def generate_code(month_year=None):
    """Génère le code d'accès - Même algorithme que le système principal"""
    if month_year is None:
        current_date = datetime.now()
        month_year = f"{current_date.month:02d}-{current_date.year}"
    
    hmac_obj = hmac.new(
        SECRET_SEED.encode('utf-8'),
        month_year.encode('utf-8'),
        hashlib.sha256
    )
    
    hash_bytes = hmac_obj.digest()
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    code_chars = []
    
    for i in range(8):
        byte_val = hash_bytes[i % len(hash_bytes)] + i
        code_chars.append(chars[byte_val % len(chars)])
    
    return ''.join(code_chars)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Code pour période spécifique
        period = sys.argv[1]
        code = generate_code(period)
        print(f"Code {period}: {code}")
    else:
        # Code actuel
        current_date = datetime.now()
        code = generate_code()
        month_name = MONTH_NAMES[current_date.month]
        print(f"🔐 {month_name} {current_date.year}: {code}")
