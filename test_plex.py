#!/usr/bin/env python3
"""
Plex Connection Tester
Quick diagnostic to check Plex server connectivity
"""

import requests
import xml.etree.ElementTree as ET


# Plex details live in plex_config.json (git-ignored). Copy plex_config.example.json to create it.
import json, os
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "plex_config.json")) as _f:
    _cfg = json.load(_f)
PLEX_URL = _cfg["plex_url"]
PLEX_TOKEN = _cfg["plex_token"]

print("=" * 60)
print("🔌 PLEX CONNECTION TEST")
print("=" * 60)

# Test 1: Can we reach the server?
print(f"\n1️⃣  Testing basic connection to: {PLEX_URL}")
try:
    response = requests.get(PLEX_URL, timeout=5)
    print(f"   ✅ Server is reachable (HTTP {response.status_code})")
except requests.exceptions.ConnectionError:
    print(f"   ❌ Cannot connect - server is DOWN or unreachable")
    print(f"   → Check: Is Plex Media Server running?")
    exit(1)
except requests.exceptions.Timeout:
    print(f"   ⏱️  Connection timed out - server is slow")
    print(f"   → Try again in a moment")
    exit(1)
except Exception as e:
    print(f"   ❌ Error: {e}")
    exit(1)

# Test 2: Can we authenticate with token?
print(f"\n2️⃣  Testing authentication with token...")
try:
    url = f"{PLEX_URL}/identity?X-Plex-Token={PLEX_TOKEN}"
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    print(f"   ✅ Authentication successful")
except requests.exceptions.HTTPError as e:
    print(f"   ❌ Authentication failed (HTTP {response.status_code})")
    print(f"   → Invalid token? Check your auth token")
    exit(1)
except Exception as e:
    print(f"   ❌ Error: {e}")
    exit(1)

# Test 3: Can we get library sections?
print(f"\n3️⃣  Fetching library sections...")
try:
    url = f"{PLEX_URL}/library/sections?X-Plex-Token={PLEX_TOKEN}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    
    root = ET.fromstring(response.content)
    sections = root.findall('Directory')
    
    print(f"   ✅ Found {len(sections)} libraries:")
    
    music_found = False
    for section in sections:
        section_type = section.get('type')
        title = section.get('title')
        section_id = section.get('key')
        print(f"      - {title} (type: {section_type}, id: {section_id})")
        
        if section_type == 'artist':
            music_found = True
            music_id = section_id
    
    if not music_found:
        print(f"   ⚠️  No Music library found!")
        print(f"   → You may need to enable Music library in Plex")
        exit(1)
    
except Exception as e:
    print(f"   ❌ Error fetching sections: {e}")
    exit(1)

# Test 4: Can we get albums from Music library?
print(f"\n4️⃣  Fetching albums from Music library...")
try:
    url = f"{PLEX_URL}/library/sections/{music_id}/all?X-Plex-Token={PLEX_TOKEN}&type=9"  # type=9 is album
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    
    root = ET.fromstring(response.content)
    albums = root.findall('Directory')
    
    print(f"   ✅ Successfully retrieved {len(albums)} albums")
    
    if len(albums) > 0:
        print(f"\n   Sample albums:")
        for album in albums[:5]:
            title = album.get('title', 'Unknown')
            print(f"      - {title}")
    
except Exception as e:
    print(f"   ❌ Error fetching albums: {e}")
    exit(1)

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED!")
print("Your Plex server is working correctly.")
print("=" * 60)
