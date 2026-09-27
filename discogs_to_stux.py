#!/usr/bin/env python3
"""
Discogs to Stux on Wax Converter
Imports Discogs CSV collection and syncs with digitized_vinyl folder
Creates progress.json with correct format for Stux on Wax dashboard
"""

import csv
from pathlib import Path
import json
from datetime import datetime
import requests
import time
import xml.etree.ElementTree as ET

class DiscogsToStuxConverter:
    def __init__(self, csv_file="stuartmcneil-collection-20260909-1530.csv", progress_file="progress.json", 
                 plex_url="http://localhost:32400", plex_token=""):
        self.csv_file = Path(csv_file)
        self.progress_file = Path(progress_file)
        self.digitized_folder = Path("digitized_vinyl")
        self.plex_url = plex_url
        self.plex_token = plex_token
        self.plex_music_library = None
        self.plex_albums = {}
        self.discogs_records = []
        self.digitized_albums = {}
        self.state = {"items": {}, "extra": []}
        
    def parse_csv(self):
        """Parse Discogs CSV export"""
        print(f"📖 Reading Discogs CSV: {self.csv_file}")
        
        if not self.csv_file.exists():
            print(f"❌ CSV file not found: {self.csv_file}")
            return False
        
        try:
            with open(self.csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.discogs_records.append({
                        'id': int(row.get('release_id', 0)) if row.get('release_id', '').isdigit() else 0,
                        'artist': row.get('Artist', ''),
                        'title': row.get('Title', ''),
                        'year': int(row.get('Released', 0)) if row.get('Released', '').isdigit() else None,
                        'format': row.get('Format', ''),
                        'label': row.get('Label', ''),
                        'catno': row.get('Catalog#', ''),
                        'genres': [],
                        'styles': [],
                        'cover': None,
                        'added': row.get('Date Added', '').split()[0] if row.get('Date Added') else ''
                    })
            
            print(f"✅ Loaded {len(self.discogs_records)} records from Discogs")
            return True
            
        except Exception as e:
            print(f"❌ Error reading CSV: {e}")
            return False
    
    def scan_plex(self):
        """Scan Plex Music library for imported albums"""
        if not self.plex_token:
            print("⚠️  No Plex token provided, skipping Plex scan")
            return True
        
        print(f"🎵 Scanning Plex server: {self.plex_url}")
        
        try:
            # Find Music library
            sections_url = f"{self.plex_url}/library/sections?X-Plex-Token={self.plex_token}"
            sections_response = requests.get(sections_url, timeout=10)
            sections_response.raise_for_status()
            
            # Parse XML to find Music library
            sections_root = ET.fromstring(sections_response.content)
            
            music_library_id = None
            for section in sections_root.findall('Directory'):
                if section.get('type') == 'artist':  # Music libraries are type 'artist'
                    music_library_id = section.get('key')
                    print(f"  ✅ Found Music library: {section.get('title')}")
                    break
            
            if not music_library_id:
                print("❌ Music library not found in Plex")
                return False
            
            # Get all albums from Music library
            albums_url = f"{self.plex_url}/library/sections/{music_library_id}/all?X-Plex-Token={self.plex_token}&type=9"  # type=9 is album
            albums_response = requests.get(albums_url, timeout=10)
            albums_response.raise_for_status()
            
            albums_root = ET.fromstring(albums_response.content)
            
            for album in albums_root.findall('Directory'):
                artist = album.find('..').get('title', 'Unknown')  # Get artist from parent
                title = album.get('title', '')
                album_id = album.get('ratingKey', '')
                
                # Get track count from Plex
                tracks_url = f"{self.plex_url}/library/metadata/{album_id}/children?X-Plex-Token={self.plex_token}"
                tracks_response = requests.get(tracks_url, timeout=10)
                track_count = len(tracks_response.content.count(b'<Track'))
                
                key = f"{artist}|{title}"
                self.plex_albums[key] = {
                    'artist': artist,
                    'album': title,
                    'tracks': track_count
                }
            
            print(f"  ✅ Found {len(self.plex_albums)} albums in Plex Music")
            return True
            
        except Exception as e:
            print(f"❌ Error connecting to Plex: {e}")
            print("   Continuing without Plex data...")
            return True  # Don't fail, just skip Plex
    
        """Parse Discogs CSV export"""
        print(f"📖 Reading Discogs CSV: {self.csv_file}")
        
        if not self.csv_file.exists():
            print(f"❌ CSV file not found: {self.csv_file}")
            return False
        
        try:
            with open(self.csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.discogs_records.append({
                        'id': int(row.get('release_id', 0)) if row.get('release_id', '').isdigit() else 0,
                        'artist': row.get('Artist', ''),
                        'title': row.get('Title', ''),
                        'year': int(row.get('Released', 0)) if row.get('Released', '').isdigit() else None,
                        'format': row.get('Format', ''),
                        'label': row.get('Label', ''),
                        'catno': row.get('Catalog#', ''),
                        'genres': [],
                        'styles': [],
                        'cover': None,
                        'added': row.get('Date Added', '').split()[0] if row.get('Date Added') else ''
                    })
            
            print(f"✅ Loaded {len(self.discogs_records)} records from Discogs")
            return True
            
        except Exception as e:
            print(f"❌ Error reading CSV: {e}")
            return False
    
    def scan_digitized(self):
        """Scan digitized_vinyl folder"""
        print(f"\n🔍 Scanning: {self.digitized_folder}")
        
        if not self.digitized_folder.exists():
            print(f"❌ Folder not found: {self.digitized_folder}")
            return False
        
        # Structure: digitized_vinyl/Artist/Album/
        for artist_dir in self.digitized_folder.iterdir():
            if not artist_dir.is_dir():
                continue
            
            artist = artist_dir.name
            
            for album_dir in artist_dir.iterdir():
                if not album_dir.is_dir():
                    continue
                
                album = album_dir.name
                track_count = 0
                
                # Count MP3/FLAC files
                for file in album_dir.iterdir():
                    if file.suffix.lower() in ['.mp3', '.flac']:
                        track_count += 1
                
                # Store for matching
                key = f"{artist}|{album}"
                self.digitized_albums[key] = {
                    'artist': artist,
                    'album': album,
                    'tracks': track_count
                }
        
        print(f"✅ Found {len(self.digitized_albums)} digitized albums")
        return True
    
    def scan_digitized(self):
        """Scan digitized_vinyl folder"""
        print(f"\n🔍 Scanning: {self.digitized_folder}")
        
        if not self.digitized_folder.exists():
            print(f"❌ Folder not found: {self.digitized_folder}")
            return False
        
        # Structure: digitized_vinyl/Artist/Album/
        for artist_dir in self.digitized_folder.iterdir():
            if not artist_dir.is_dir():
                continue
            
            artist = artist_dir.name
            
            for album_dir in artist_dir.iterdir():
                if not album_dir.is_dir():
                    continue
                
                album = album_dir.name
                track_count = 0
                
                # Count MP3/FLAC files
                for file in album_dir.iterdir():
                    if file.suffix.lower() in ['.mp3', '.flac']:
                        track_count += 1
                
                # Store for matching
                key = f"{artist}|{album}"
                self.digitized_albums[key] = {
                    'artist': artist,
                    'album': album,
                    'tracks': track_count
                }
        
        print(f"✅ Found {len(self.digitized_albums)} digitized albums")
        return True
    
    def get_expected_tracks(self, artist, album):
        """Query MusicBrainz for expected track count"""
        try:
            url = "https://musicbrainz.org/ws/2/release"
            params = {
                'query': f'artist:"{artist}" release:"{album}"',
                'fmt': 'json',
                'limit': 1
            }
            headers = {'User-Agent': 'StuxOnWax/1.0'}
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('releases'):
                release_id = data['releases'][0]['id']
                
                # Get detailed info with track count
                detail_url = f"https://musicbrainz.org/ws/2/release/{release_id}"
                detail_params = {'fmt': 'json', 'inc': 'recordings'}
                detail_response = requests.get(detail_url, params=detail_params, headers=headers, timeout=10)
                detail_response.raise_for_status()
                detail_data = detail_response.json()
                
                # Count tracks from first media
                media = detail_data.get('media', [{}])[0]
                track_count = len(media.get('tracks', []))
                
                return track_count
        except Exception as e:
            pass
        
        return None
    
    def fuzzy_match(self, s1, s2):
        """Fuzzy match for album names"""
        s1 = s1.lower().strip()
        s2 = s2.lower().strip()
        
        if s1 == s2:
            return 100
        
        # Remove punctuation and extra words
        s1_clean = s1.replace("'", "").replace("'", "").replace('"', "").replace("'s", "").replace("…", "")
        s2_clean = s2.replace("'", "").replace("'", "").replace('"', "").replace("'s", "").replace("…", "")
        
        if s1_clean == s2_clean:
            return 95
        
        # Check substring match
        if s1 in s2 or s2 in s1:
            return 80
        
        # Levenshtein-lite: check character overlap
        common = sum(1 for c in s1_clean if c in s2_clean)
        if common / max(len(s1_clean), len(s2_clean)) > 0.7:
            return 75
        
        return 0
    
    def match_and_mark(self):
        """Match Discogs records to Plex/digitized, then add Plex-only albums"""
        print(f"\n🔗 Matching Discogs to Plex/digitized albums...")
        
        plex_matches = 0
        digitized_matches = 0
        discogs_only = 0
        
        # First pass: Match Discogs albums to Plex/digitized
        for record in self.discogs_records:
            if not record['id']:
                continue
            
            record_id = str(record['id'])
            artist = record['artist']
            title = record['title']
            
            matched_location = None
            matched_data = None
            match_type = None
            
            # Priority 1: Check Plex first
            key = f"{artist}|{title}"
            if key in self.plex_albums:
                matched_location = "plex"
                matched_data = self.plex_albums[key]
                match_type = "PLEX"
            else:
                # Try fuzzy match on Plex
                best_score = 0
                best_match = None
                
                for plex_key, plex_album in self.plex_albums.items():
                    artist_score = self.fuzzy_match(artist, plex_album['artist'])
                    album_score = self.fuzzy_match(title, plex_album['album'])
                    combined_score = (artist_score + album_score) / 2
                    
                    if combined_score > best_score:
                        best_score = combined_score
                        best_match = plex_key
                
                if best_score >= 75:
                    matched_location = "plex"
                    matched_data = self.plex_albums[best_match]
                    match_type = f"PLEX-FUZZY: {best_score:.0f}%"
            
            # Priority 2: Check digitized_vinyl if not in Plex
            if not matched_location:
                if key in self.digitized_albums:
                    matched_location = "digitized"
                    matched_data = self.digitized_albums[key]
                    match_type = "DIGITIZED"
                else:
                    # Fuzzy match on digitized
                    best_score = 0
                    best_match = None
                    
                    for dig_key, dig_album in self.digitized_albums.items():
                        artist_score = self.fuzzy_match(artist, dig_album['artist'])
                        album_score = self.fuzzy_match(title, dig_album['album'])
                        combined_score = (artist_score + album_score) / 2
                        
                        if combined_score > best_score:
                            best_score = combined_score
                            best_match = dig_key
                    
                    if best_score >= 75:
                        matched_location = "digitized"
                        matched_data = self.digitized_albums[best_match]
                        match_type = f"DIGITIZED-FUZZY: {best_score:.0f}%"
            
            # Generate status note and mark
            if matched_location == "plex":
                # Album is in Plex Music
                print(f"  🔍 Checking {artist} - {title} (Plex)...")
                expected_tracks = self.get_expected_tracks(artist, title)
                actual_tracks = matched_data['tracks']
                
                if expected_tracks:
                    if actual_tracks >= expected_tracks:
                        status_note = f"In Plex - Complete ({actual_tracks}/{expected_tracks} tracks)"
                    else:
                        status_note = f"In Plex - Partial ({actual_tracks}/{expected_tracks} tracks)"
                else:
                    status_note = f"In Plex ({actual_tracks} tracks)"
                
                self.state['items'][record_id] = {
                    's': 'done',
                    'n': status_note,
                    't': datetime.now().isoformat().split('T')[0]
                }
                print(f"  ✅ {artist} - {title} [{match_type}] → {status_note}")
                plex_matches += 1
                time.sleep(0.3)
                
            elif matched_location == "digitized":
                # Album is digitized but not in Plex
                print(f"  🔍 Checking {artist} - {title} (Digitized)...")
                expected_tracks = self.get_expected_tracks(artist, title)
                actual_tracks = matched_data['tracks']
                
                if expected_tracks:
                    if actual_tracks >= expected_tracks:
                        status_note = f"Ready for Plex - Complete ({actual_tracks}/{expected_tracks} tracks)"
                    else:
                        status_note = f"Ripping - Partial ({actual_tracks}/{expected_tracks} tracks)"
                else:
                    status_note = f"Digitized ({actual_tracks} tracks)"
                
                # Mark as "ripping" if partial, "done" if complete
                status = "done" if expected_tracks and actual_tracks >= expected_tracks else "rip"
                
                self.state['items'][record_id] = {
                    's': status,
                    'n': status_note,
                    't': datetime.now().isoformat().split('T')[0]
                }
                print(f"  ✅ {artist} - {title} [{match_type}] → {status_note}")
                digitized_matches += 1
                time.sleep(0.3)
            else:
                # Discogs only - not digitized, not in Plex
                self.state['items'][record_id] = {
                    's': 'todo',
                    'n': 'In Discogs collection',
                    't': ''
                }
                discogs_only += 1
        
        print(f"\n📊 Discogs albums: {plex_matches} in Plex, {digitized_matches} digitized, {discogs_only} on shelf")
        
        # Second pass: Add Plex-only albums (not in Discogs)
        print(f"\n🎵 Adding Plex-only albums...")
        
        discogs_keys = set(f"{r['artist']}|{r['title']}" for r in self.discogs_records)
        plex_only_count = 0
        
        for plex_key, plex_album in self.plex_albums.items():
            if plex_key not in discogs_keys:
                # This Plex album is not in Discogs collection
                new_record = {
                    'id': 0,  # No Discogs ID
                    'artist': plex_album['artist'],
                    'title': plex_album['album'],
                    'year': None,
                    'format': '',
                    'label': '',
                    'catno': '',
                    'genres': [],
                    'styles': [],
                    'cover': None,
                    'added': ''
                }
                self.discogs_records.append(new_record)
                
                # Add to extra array so it's tracked separately
                self.state['extra'].append(new_record)
                
                status_note = f"In Plex - {plex_album['tracks']} tracks (Not in Discogs)"
                # Use artist + album as a pseudo-ID for Plex-only albums
                pseudo_id = f"plex_{plex_key.replace('|', '_')}"
                
                self.state['items'][pseudo_id] = {
                    's': 'done',
                    'n': status_note,
                    't': ''
                }
                plex_only_count += 1
        
        print(f"  ✅ Added {plex_only_count} Plex-only albums")
        
        total_matched = plex_matches + digitized_matches + discogs_only + plex_only_count
        print(f"\n📊 Total matched: {total_matched} albums")
        return total_matched
    
    def save_progress(self):
        """Save progress.json for Stux on Wax"""
        # Add all Discogs records to state
        self.state['records'] = self.discogs_records
        
        try:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=1, ensure_ascii=False)
            print(f"\n✅ Saved: {self.progress_file}")
            return True
        except Exception as e:
            print(f"❌ Error saving: {e}")
            return False
    
    def save_progress(self):
        """Save progress.json for Stux on Wax"""
        # Add all Discogs records to state
        self.state['records'] = self.discogs_records
        
        try:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=1, ensure_ascii=False)
            print(f"\n✅ Saved: {self.progress_file}")
            return True
        except Exception as e:
            print(f"❌ Error saving: {e}")
            return False
    
    def print_stats(self):
        """Print collection stats"""
        total = len(self.discogs_records)
        in_plex = len([s for s in self.state['items'].values() if s.get('s') == 'done'])
        ripping = len([s for s in self.state['items'].values() if s.get('s') == 'rip'])
        shelf = len([s for s in self.state['items'].values() if s.get('s') == 'todo'])
        
        print(f"\n" + "=" * 60)
        print(f"📊 COLLECTION STATS")
        print(f"=" * 60)
        print(f"  Total catalogue: {total}")
        print(f"    ✅ In Plex Music: {in_plex}")
        print(f"    🔄 Ripping/Digitized: {ripping}")
        print(f"    📚 On Shelf (Discogs): {shelf}")
        print(f"  Plex-only albums: {len(self.state.get('extra', []))}")
        print(f"  Overall completion: {100*in_plex//total}% in Plex")
        print(f"=" * 60)
    
    def run(self):
        """Execute conversion workflow"""
        print("=" * 60)
        print("🎵 DISCOGS → STUX ON WAX CONVERTER (with Plex)")
        print("=" * 60)
        
        if not self.parse_csv():
            return False
        
        if self.plex_token:
            if not self.scan_plex():
                print("⚠️  Plex scan failed, continuing with digitized_vinyl only")
        
        if not self.scan_digitized():
            return False
        
        self.match_and_mark()
        
        if not self.save_progress():
            return False
        
        self.print_stats()
        
        print("\n✅ CONVERSION COMPLETE!")
        print("Next step: Open index.html and import progress.json")
        return True


def main():
    # Plex details live in plex_config.json (git-ignored). Copy plex_config.example.json to create it.
    import os
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "plex_config.json")) as f:
        cfg = json.load(f)
    plex_url = cfg["plex_url"]
    plex_token = cfg["plex_token"]
    
    converter = DiscogsToStuxConverter(plex_url=plex_url, plex_token=plex_token)
    success = converter.run()
    exit(0 if success else 1)


if __name__ == '__main__':
    main()
