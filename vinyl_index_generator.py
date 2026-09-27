#!/usr/bin/env python3
"""
Vinyl Index Generator - Scans digitized_vinyl folder and generates index.html
Shows all digitized albums with cover art and status
"""

import os
from pathlib import Path
import json
from datetime import datetime

class VinylIndexGenerator:
    def __init__(self, digitized_folder="digitized_vinyl"):
        self.digitized_folder = Path(digitized_folder)
        self.albums = []
        self.output_file = Path("index.html")
        
    def scan_albums(self):
        """Scan digitized_vinyl folder for albums"""
        print(f"🔍 Scanning: {self.digitized_folder}")
        print(f"   Full path: {self.digitized_folder.absolute()}")
        
        if not self.digitized_folder.exists():
            print(f"❌ Folder not found: {self.digitized_folder}")
            print(f"   Checked at: {self.digitized_folder.absolute()}")
            return False
        
        # List what's in the folder
        try:
            items = list(self.digitized_folder.iterdir())
            print(f"   Found {len(items)} items in digitized_vinyl")
        except Exception as e:
            print(f"❌ Error reading folder: {e}")
            return False
        
        # Structure: digitized_vinyl/Artist/Album/
        for artist_dir in self.digitized_folder.iterdir():
            if not artist_dir.is_dir():
                continue
            
            artist = artist_dir.name
            print(f"   Processing artist: {artist}")
            
            for album_dir in artist_dir.iterdir():
                if not album_dir.is_dir():
                    continue
                
                album = album_dir.name
                cover_art = None
                track_count = 0
                
                # Look for cover art and count tracks
                try:
                    for file in album_dir.iterdir():
                        if file.name.lower() == 'cover.jpg':
                            cover_art = f"digitized_vinyl/{artist}/{album}/cover.jpg"
                        elif file.suffix.lower() in ['.mp3', '.flac']:
                            track_count += 1
                except Exception as e:
                    print(f"   ⚠️  Error reading {album}: {e}")
                    continue
                
                self.albums.append({
                    'artist': artist,
                    'album': album,
                    'tracks': track_count,
                    'cover_art': cover_art,
                    'status': 'Digitized',
                    'date_added': datetime.now().strftime('%Y-%m-%d')
                })
                
                print(f"     ✅ {artist} - {album} ({track_count} tracks)")
        
        print(f"\n📊 Total albums found: {len(self.albums)}")
        return True
    
    def generate_html(self):
        """Generate HTML index"""
        print("\n📝 Generating index.html...")
        
        # Sort albums by artist, then album
        self.albums.sort(key=lambda x: (x['artist'].lower(), x['album'].lower()))
        
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stux on Wax - Digitized Vinyl Collection</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #333;
            padding: 20px;
            min-height: 100vh;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            color: white;
            margin-bottom: 40px;
        }
        
        h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .subtitle {
            font-size: 1.1em;
            opacity: 0.9;
        }
        
        .stats {
            display: flex;
            justify-content: center;
            gap: 40px;
            margin-top: 20px;
            font-size: 1.1em;
        }
        
        .stat-item {
            background: rgba(255,255,255,0.1);
            padding: 10px 20px;
            border-radius: 5px;
            backdrop-filter: blur(10px);
        }
        
        .album-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }
        
        .album-card {
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            cursor: pointer;
        }
        
        .album-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 12px rgba(0,0,0,0.2);
        }
        
        .album-cover {
            width: 100%;
            aspect-ratio: 1;
            background: #f0f0f0;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }
        
        .album-cover img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        .album-cover-placeholder {
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 2em;
        }
        
        .album-info {
            padding: 15px;
        }
        
        .album-artist {
            font-size: 0.9em;
            color: #666;
            margin-bottom: 5px;
        }
        
        .album-title {
            font-weight: bold;
            margin-bottom: 8px;
            font-size: 1em;
        }
        
        .album-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.85em;
        }
        
        .status-badge {
            background: #4CAF50;
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
        }
        
        .track-count {
            color: #999;
        }
        
        footer {
            text-align: center;
            color: white;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.2);
        }
        
        .last-updated {
            font-size: 0.9em;
            opacity: 0.8;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎵 Stux on Wax</h1>
            <p class="subtitle">Digitized Vinyl Collection</p>
            <div class="stats">
                <div class="stat-item">
                    <strong>Albums:</strong> """ + str(len(self.albums)) + """
                </div>
                <div class="stat-item">
                    <strong>Total Tracks:</strong> """ + str(sum(a['tracks'] for a in self.albums)) + """
                </div>
            </div>
        </header>
        
        <div class="album-grid">
"""
        
        # Add each album
        for album in self.albums:
            html += f"""            <div class="album-card">
                <div class="album-cover">
"""
            if album['cover_art'] and os.path.exists(album['cover_art']):
                html += f'                    <img src="{album["cover_art"]}" alt="{album["album"]}">\n'
            else:
                html += '                    <div class="album-cover-placeholder">♫</div>\n'
            
            html += f"""                </div>
                <div class="album-info">
                    <div class="album-artist">{album['artist']}</div>
                    <div class="album-title">{album['album']}</div>
                    <div class="album-meta">
                        <span class="track-count">{album['tracks']} tracks</span>
                        <span class="status-badge">{album['status']}</span>
                    </div>
                </div>
            </div>
"""
        
        html += """        </div>
        
        <footer>
            <p class="last-updated">Last updated: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
            <p>Collection stored in Plex</p>
        </footer>
    </div>
</body>
</html>
"""
        
        # Write HTML file
        self.output_file.write_text(html, encoding='utf-8')
        print(f"✅ Generated: {self.output_file}")
        
        return True
    
    def generate_progress_json(self):
        """Generate progress.json for tracking"""
        progress = {
            'total_albums': len(self.albums),
            'total_tracks': sum(a['tracks'] for a in self.albums),
            'albums_digitized': len(self.albums),
            'completion_percent': 100,
            'last_updated': datetime.now().isoformat(),
            'albums': self.albums
        }
        
        with open('progress.json', 'w') as f:
            json.dump(progress, f, indent=2)
        
        print(f"✅ Generated: progress.json")
        return True
    
    def run(self):
        """Execute full index generation workflow"""
        print("=" * 60)
        print("🎙️  VINYL INDEX GENERATOR")
        print("=" * 60)
        
        if not self.scan_albums():
            return False
        
        if not self.generate_html():
            return False
        
        if not self.generate_progress_json():
            return False
        
        print("\n" + "=" * 60)
        print("✅ INDEX UPDATED!")
        print(f"📁 Output: index.html")
        print("=" * 60)
        return True


def main():
    generator = VinylIndexGenerator()
    success = generator.run()
    exit(0 if success else 1)


if __name__ == '__main__':
    main()
