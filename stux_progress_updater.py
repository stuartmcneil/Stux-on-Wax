#!/usr/bin/env python3
"""
Stux on Wax Progress Updater
Scans digitized_vinyl folder and updates progress.json to mark completed albums
Preserves all existing Discogs data and manual notes
"""

import json
from pathlib import Path
from datetime import datetime

class StuxOnWaxUpdater:
    def __init__(self, progress_file="progress.json"):
        self.progress_file = Path(progress_file)
        self.digitized_folder = Path("digitized_vinyl")
        self.state = None
        self.digitized_albums = {}
        
    def load_progress(self):
        """Load existing progress.json"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
                print(f"✅ Loaded progress: {self.progress_file}")
                return True
            except Exception as e:
                print(f"❌ Error loading progress: {e}")
                return False
        else:
            print(f"⚠️  Progress file not found, will create new one")
            self.state = {"items": {}, "extra": []}
            return True
    
    def scan_digitized(self):
        """Scan digitized_vinyl folder for completed albums"""
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
                    'tracks': track_count,
                    'path': str(album_dir)
                }
                print(f"  ✅ {artist} - {album} ({track_count} tracks)")
        
        print(f"\n📊 Found {len(self.digitized_albums)} digitized albums")
        return True
    
    def fuzzy_match(self, s1, s2):
        """Simple fuzzy match for album names (handles minor variations)"""
        s1 = s1.lower().strip()
        s2 = s2.lower().strip()
        if s1 == s2:
            return 100
        # Remove common words and punctuation
        s1_clean = s1.replace("'", "").replace("'", "").replace('"', "").replace("'s", "")
        s2_clean = s2.replace("'", "").replace("'", "").replace('"', "").replace("'s", "")
        if s1_clean == s2_clean:
            return 90
        # Check if one contains the other
        if s1 in s2 or s2 in s1:
            return 70
        return 0
    
    def match_discogs_to_digitized(self, records):
        """Match Discogs records to digitized albums and mark as complete"""
        print(f"\n🔗 Matching Discogs to digitized albums...")
        
        matches = 0
        for record in records:
            artist = record.get('artist', '').strip()
            title = record.get('title', '').strip()
            record_id = str(record.get('id', ''))
            
            # Try exact match first
            key = f"{artist}|{title}"
            if key in self.digitized_albums:
                self.mark_as_done(record_id, artist, title)
                matches += 1
                continue
            
            # Try fuzzy match
            best_match = None
            best_score = 0
            for dig_key, dig_album in self.digitized_albums.items():
                # Match both artist and album
                artist_score = self.fuzzy_match(artist, dig_album['artist'])
                album_score = self.fuzzy_match(title, dig_album['album'])
                combined_score = (artist_score + album_score) / 2
                
                if combined_score > best_score:
                    best_score = combined_score
                    best_match = dig_key
            
            if best_score >= 70:  # High confidence match
                dig_album = self.digitized_albums[best_match]
                self.mark_as_done(record_id, dig_album['artist'], dig_album['album'])
                matches += 1
        
        print(f"✅ Matched and marked {matches} albums as complete")
        return matches
    
    def mark_as_done(self, record_id, artist, album):
        """Mark a record as done in progress state"""
        record_id_str = str(record_id)
        
        # Preserve existing state or create new
        if record_id_str in self.state.get('items', {}):
            existing = self.state['items'][record_id_str]
            # Keep existing notes, update status and today's date
            self.state['items'][record_id_str] = {
                's': 'done',
                'n': existing.get('n', ''),
                't': datetime.now().isoformat().split('T')[0]
            }
        else:
            # New entry
            self.state['items'][record_id_str] = {
                's': 'done',
                'n': '',
                't': datetime.now().isoformat().split('T')[0]
            }
        
        print(f"  ✅ {artist} - {album}")
    
    def save_progress(self):
        """Save updated progress.json"""
        try:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=1, ensure_ascii=False)
            print(f"\n✅ Saved progress to: {self.progress_file}")
            return True
        except Exception as e:
            print(f"❌ Error saving progress: {e}")
            return False
    
    def run(self):
        """Execute full update workflow"""
        print("=" * 60)
        print("🎵 STUX ON WAX - PROGRESS UPDATER")
        print("=" * 60)
        
        # Load existing progress
        if not self.load_progress():
            return False
        
        # Scan digitized albums
        if not self.scan_digitized():
            return False
        
        # Get records from state
        all_records = []
        
        # Add records from main state (if using Discogs import)
        if 'records' in self.state:
            all_records.extend(self.state['records'])
        
        # Add records from extra (manually added)
        if 'extra' in self.state:
            all_records.extend(self.state['extra'])
        
        if not all_records:
            print("⚠️  No records found in progress file")
            return False
        
        # Match and update
        self.match_discogs_to_digitized(all_records)
        
        # Save updated progress
        if not self.save_progress():
            return False
        
        print("\n" + "=" * 60)
        print("✅ PROGRESS UPDATED!")
        print("=" * 60)
        return True


def main():
    updater = StuxOnWaxUpdater()
    success = updater.run()
    exit(0 if success else 1)


if __name__ == '__main__':
    main()
