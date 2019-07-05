#!/usr/bin/env python3

# tg3442_firewall - Simple tool to manipulate the Arris TG3442 router firewall
# Copyright (c) 2019 Sven Hesse <drmccoy@drmccoy.de>
#
# Permission to use, copy, and modify this software with or without fee
# is hereby granted, provided that this entire notice is included in
# all source code copies of any software which is or includes a copy or
# modification of this software.
#
# THIS SOFTWARE IS BEING PROVIDED "AS IS", WITHOUT ANY EXPRESS OR
# IMPLIED WARRANTY. IN PARTICULAR, NONE OF THE AUTHORS MAKES ANY
# REPRESENTATION OR WARRANTY OF ANY KIND CONCERNING THE
# MERCHANTABILITY OF THIS SOFTWARE OR ITS FITNESS FOR ANY PARTICULAR
# PURPOSE.
#
#
# tg3442_firewall is based on the Arris TG3442 MUNIN plugin by Daniel Hiepler
# (<https://github.com/heeplr/contrib/blob/patch-1/plugins/router/arris-tg3442>).
# The original copyright notice on said plugin reads:
#
# Copyright (c) 2019 Daniel Hiepler <d-munin@coderdu.de>
#
# Permission to use, copy, and modify this software with or without fee
# is hereby granted, provided that this entire notice is included in
# all source code copies of any software which is or includes a copy or
# modification of this software.
#
# THIS SOFTWARE IS BEING PROVIDED "AS IS", WITHOUT ANY EXPRESS OR
# IMPLIED WARRANTY. IN PARTICULAR, NONE OF THE AUTHORS MAKES ANY
# REPRESENTATION OR WARRANTY OF ANY KIND CONCERNING THE
# MERCHANTABILITY OF THIS SOFTWARE OR ITS FITNESS FOR ANY PARTICULAR
# PURPOSE.


import binascii
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
import hashlib
import json
import re
import requests
import sys
import os

def login(session, url, username, password):
    """ Log in """

    # Get login page, parse and read session ID
    r = session.get(f"{url}")
    h = BeautifulSoup(r.text, "lxml")
    current_session_id = re.search(r".*var currentSessionId = '(.+)';.*", h.head.text)[1]

    # Encrypt password
    salt = os.urandom(8)
    iv = os.urandom(8)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        bytes(password.encode("ascii")),
        salt,
        iterations=1000,
        dklen=128/8
    )
    secret = { "Password": password, "Nonce": current_session_id }
    plaintext = bytes(json.dumps(secret).encode("ascii"))
    associated_data = "loginPassword"
    cipher = AES.new(key, AES.MODE_CCM, iv)
    cipher.update(bytes(associated_data.encode("ascii")))
    encrypt_data = cipher.encrypt(plaintext)
    encrypt_data += cipher.digest()
    login_data = {
        'EncryptData': binascii.hexlify(encrypt_data).decode("ascii"),
        'Name': username,
        'Salt': binascii.hexlify(salt).decode("ascii"),
        'Iv': binascii.hexlify(iv).decode("ascii"),
        'AuthData': associated_data
    }

    # Log in
    r = session.put(
        f"{url}/php/ajaxSet_Password.php",
        headers={
            "Content-Type": "application/json",
            "csrfNonce": "undefined"
        },
        data=json.dumps(login_data)
    )

    # Parse result and remember CSRF nonce
    result = json.loads(r.text)
    if result['p_status'] == "Fail":
        print("Login failure", file=sys.stderr)
        exit(1)
    csrf_nonce = result['nonce']

    # Prepare headers and set credentials cookie
    session.headers.update({
        "X-Requested-With": "XMLHttpRequest",
        "csrfNonce": csrf_nonce,
        "Origin": f"{url}/",
        "Referer": f"{url}/"
    })
    session.cookies.set(
        "credential",
        "eyAidW5pcXVlIjoiMjgwb2FQU0xpRiIsICJmYW1pbHkiOiI4NTIiLCAibW9kZWxuYW1lIjoiV"
        "EcyNDkyTEctODUiLCAibmFtZSI6InRlY2huaWNpYW4iLCAidGVjaCI6dHJ1ZSwgIm1vY2EiOj"
        "AsICJ3aWZpIjo1LCAiY29uVHlwZSI6IldBTiIsICJnd1dhbiI6ImYiLCAiRGVmUGFzc3dkQ2h"
        "hbmdlZCI6IllFUyIgfQ=="
    )

    # Set session
    r = session.post(f"{url}/php/ajaxSet_Session.php")

def get_firewall_status(session, url):
    """ Query the current firewall status """

    r = session.get(f"{url}/php/net_firewall_data.php", params={'fwData[FirewallLevel]': ""})
    status = json.loads(r.text)
    if status['FirewallLevel'] == "None":
        return False

    return True

def print_firewall_status(status):
    print("Firewall is", "enabled" if status else "disabled")

def set_firewall(session, url, enable):
    """ Set the firewall status """

    y = json.dumps({ "fwEnable": "true" if enable else "false" })
    r = session.post(f"{url}/php/ajaxSet_net_firewall_data.php", data={'fwData': y})

def main():
    if len(sys.argv) != 5:
        print("Usage:", sys.argv[0], "<URL> <username> <password> <command>")
        print("Valid commands are:")
        print("    status")
        print("    on")
        print("    off")
        print("    toggle")
        print("    forceon")
        print("    forceoff")
        exit(1)

    url = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    command = sys.argv[4]

    session = requests.Session()
    login(session, url, username, password)

    if command == "status":
        print_firewall_status(get_firewall_status(session, url))
    elif command == "on":
        print("Switching firewall on")
        set_firewall(session, url, True)
        print_firewall_status(get_firewall_status(session, url))
    elif command == "off":
        print("Switching firewall off")
        set_firewall(session, url, False)
        print_firewall_status(get_firewall_status(session, url))
    elif command == "toggle":
        status = get_firewall_status(session, url)
        print_firewall_status(status)
        print("Toggling firewall")
        set_firewall(session, url, not status)
        print_firewall_status(get_firewall_status(session, url))
    elif command == "forceon":
        print("Forcing firewall on")
        set_firewall(session, url, False)
        set_firewall(session, url, True)
        print_firewall_status(get_firewall_status(session, url))
    elif command == "forceoff":
        print("Forcing firewall off")
        set_firewall(session, url, True)
        set_firewall(session, url, False)
        print_firewall_status(get_firewall_status(session, url))
    else:
        print("Unknown command", command, file=sys.stderr)
        exit(1)

if __name__== "__main__":
    main()
