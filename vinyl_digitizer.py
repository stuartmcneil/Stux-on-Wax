#!/usr/bin/env python3
"""
Vinyl Digitizer - Automate recording, splitting, tagging, and organizing vinyl records
Queries MusicBrainz for metadata, splits audio by track duration, embeds tags and artwork
"""

import os
import sys
import json
import subprocess
import requests
from pathlib import Path
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, APIC, TRCK
from mutagen.flac import FLAC
from mutagen.flac import Picture
import urllib.request
import time

class VinylDigitizer:
    def __init__(self, input_file, artist, album, output_format='mp3'):
        self.input_file = input_file
        self.artist = artist
        self.album = album
        self.output_format = output_format.lower()
        self.metadata = None
        self.temp_dir = Path("temp_split")
        self.temp_dir.mkdir(exist_ok=True)
        
        # FFmpeg path configuration
        self.ffmpeg_path = r'C:\ffmpeg\bin\ffmpeg.exe'
        if not os.path.exists(self.ffmpeg_path):
            print(f"⚠️  FFmpeg not found at {self.ffmpeg_path}")
            print("Please ensure FFmpeg is extracted to C:\\ffmpeg")
            sys.exit(1)
        
        # output_dir will be set after metadata is retrieved
        self.output_dir = None
        
    def search_musicbrainz(self):
        """Query MusicBrainz for album metadata by Release ID or search"""
        headers = {'User-Agent': 'VinylDigitizer/1.0'}
        
        # Check if artist parameter is actually a Release ID
        is_release_id = len(self.artist) == 36 and self.artist.count('-') == 4
        
        if is_release_id:
            print(f"\n🔍 Looking up MusicBrainz Release ID: {self.artist}")
            release_id = self.artist
        else:
            print(f"\n🔍 Searching MusicBrainz for: {self.artist} - {self.album}")
            
            # MusicBrainz API endpoint
            url = "https://musicbrainz.org/ws/2/release"
            params = {
                'query': f'artist:"{self.artist}" release:"{self.album}"',
                'fmt': 'json',
                'limit': 1
            }
            
            try:
                response = requests.get(url, params=params, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if not data['releases']:
                    print("❌ Album not found on MusicBrainz. Please check spelling.")
                    return False
                
                release_id = data['releases'][0]['id']
            except requests.exceptions.RequestException as e:
                print(f"❌ Error connecting to MusicBrainz: {e}")
                return False
        
        # Get detailed release info including recordings
        try:
            detail_url = f"https://musicbrainz.org/ws/2/release/{release_id}"
            detail_params = {'fmt': 'json', 'inc': 'recordings'}
            
            detail_response = requests.get(detail_url, params=detail_params, headers=headers, timeout=10)
            detail_response.raise_for_status()
            detail_data = detail_response.json()
            
            self.metadata = {
                'title': detail_data.get('title', self.album if not is_release_id else 'Unknown'),
                'artist': detail_data.get('artist-credit')[0]['artist']['name'] if detail_data.get('artist-credit') else self.artist,
                'date': detail_data.get('date', 'Unknown'),
                'tracks': [],
                'cover_art_url': None
            }
            
            # Create output directory with proper artist/album names
            self.output_dir = Path(f"digitized_vinyl/{self.metadata['artist']}/{self.metadata['title']}")
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            # Extract track info
            media = detail_data.get('media', [{}])[0]
            for track_data in media.get('tracks', []):
                recording = track_data.get('recording', {})
                self.metadata['tracks'].append({
                    'number': track_data.get('position', len(self.metadata['tracks']) + 1),
                    'title': recording.get('title', f'Track {track_data.get("position", 1)}'),
                    'duration_ms': recording.get('length', 0),
                    'artist': self.metadata['artist']
                })
            
            # Try to get cover art
            self.get_cover_art(release_id)
            
            print(f"✅ Found album: {self.metadata['artist']} - {self.metadata['title']}")
            print(f"✅ {len(self.metadata['tracks'])} tracks")
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error connecting to MusicBrainz: {e}")
            return False
    
    def get_cover_art(self, release_id):
        """Fetch cover art from Cover Art Archive"""
        print("📷 Fetching cover art...")
        try:
            # Ensure output directory exists
            self.output_dir.mkdir(parents=True, exist_ok=True)
            art_url = f"https://coverartarchive.org/release/{release_id}/front-500"
            urllib.request.urlretrieve(art_url, self.output_dir / "cover.jpg")
            self.metadata['cover_art_url'] = str(self.output_dir / "cover.jpg")
            print("✅ Cover art saved")
        except Exception as e:
            print(f"⚠️  No cover art found: {e}")
    
    def get_audio_duration(self):
        """Get total duration of audio file in seconds"""
        try:
            cmd = [
                self.ffmpeg_path,
                '-i', self.input_file
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            output = result.stderr
            
            # Look for "Duration: HH:MM:SS.ms"
            import re
            match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', output)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = float(match.group(3))
                total_seconds = hours * 3600 + minutes * 60 + seconds
                return total_seconds
        except Exception as e:
            print(f"⚠️  Could not determine audio duration: {e}")
        return None
    
    def limit_tracks_to_recording(self):
        """Remove tracks that exceed the audio file duration"""
        audio_duration = self.get_audio_duration()
        
        if audio_duration is None:
            print("⚠️  Could not auto-detect duration, using all tracks")
            return
        
        print(f"\n📊 Audio duration: {audio_duration/60:.1f} minutes")
        
        # Calculate how long all tracks should take
        total_track_time = 0
        tracks_that_fit = []
        
        for track in self.metadata['tracks']:
            duration_sec = track['duration_ms'] / 1000
            if total_track_time + duration_sec <= audio_duration:
                total_track_time += duration_sec
                tracks_that_fit.append(track)
            else:
                break
        
        original_count = len(self.metadata['tracks'])
        new_count = len(tracks_that_fit)
        
        if new_count < original_count:
            print(f"⚠️  Found {original_count} tracks on MusicBrainz, but only {new_count} fit in recording")
            print(f"    Using first {new_count} tracks")
            self.metadata['tracks'] = tracks_that_fit
        else:
            print(f"✅ All {original_count} tracks fit in recording")
    
    def split_audio(self):
        """Split audio file by track duration"""
        print("\n✂️  Splitting audio by track duration...")
        
        if not self.metadata or not self.metadata['tracks']:
            print("❌ No track metadata available for splitting")
            return False
        
        try:
            start_time = 0
            for i, track in enumerate(self.metadata['tracks']):
                duration_sec = track['duration_ms'] / 1000
                end_time = start_time + duration_sec
                
                track_num = track['number']
                output_file = self.temp_dir / f"track_{track_num:02d}.wav"
                
                # Use FFmpeg to extract segment
                cmd = [
                    self.ffmpeg_path,
                    '-i', self.input_file,
                    '-ss', str(start_time),
                    '-to', str(end_time),
                    '-c', 'copy',
                    '-y',
                    str(output_file)
                ]
                
                subprocess.run(cmd, capture_output=True, check=True)
                print(f"  ✅ Track {track_num}: {track['title']} ({duration_sec:.1f}s)")
                
                start_time = end_time
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg error: {e.stderr.decode()}")
            return False
    
    def convert_and_tag(self):
        """Convert to target format and embed metadata"""
        print(f"\n🎵 Converting to {self.output_format.upper()} and embedding metadata...")
        
        if not self.metadata or not self.output_dir:
            print("❌ No metadata or output directory available")
            return False
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            for track in self.metadata['tracks']:
                track_num = track['number']
                input_wav = self.temp_dir / f"track_{track_num:02d}.wav"
                
                # Sanitize track title for valid filename
                safe_title = self.sanitize_filename(track['title'])
                
                if self.output_format == 'mp3':
                    output_file = self.output_dir / f"{track_num:02d} - {safe_title}.mp3"
                    # Convert to MP3
                    cmd = [
                        self.ffmpeg_path,
                        '-i', str(input_wav),
                        '-q:a', '0',  # Highest quality
                        '-y',
                        str(output_file)
                    ]
                    subprocess.run(cmd, capture_output=True, check=True)
                    
                    # Tag MP3
                    self.tag_mp3(output_file, track)
                    
                elif self.output_format == 'flac':
                    output_file = self.output_dir / f"{track_num:02d} - {safe_title}.flac"
                    # Convert to FLAC
                    cmd = [
                        self.ffmpeg_path,
                        '-i', str(input_wav),
                        '-c:a', 'flac',
                        '-y',
                        str(output_file)
                    ]
                    subprocess.run(cmd, capture_output=True, check=True)
                    
                    # Tag FLAC
                    self.tag_flac(output_file, track)
                
                print(f"  ✅ {track_num:02d} - {safe_title}")
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Conversion error: {e}")
            return False
    
    def tag_mp3(self, filename, track):
        """Embed ID3 tags in MP3"""
        try:
            audio = MP3(filename)
            audio.add_tags()
            
            audio['TIT2'] = TIT2(encoding=3, text=[track['title']])
            audio['TPE1'] = TPE1(encoding=3, text=[self.artist])
            audio['TALB'] = TALB(encoding=3, text=[self.album])
            audio['TDRC'] = TDRC(encoding=3, text=[self.metadata['date']])
            audio['TRCK'] = TRCK(encoding=3, text=[str(track['number'])])
            
            # Embed cover art if available
            if self.metadata.get('cover_art_url'):
                with open(self.metadata['cover_art_url'], 'rb') as f:
                    audio['APIC'] = APIC(encoding=3, mime='image/jpeg', type=3, desc='', data=f.read())
            
            audio.save()
        except Exception as e:
            print(f"  ⚠️  Error tagging {filename}: {e}")
    
    def tag_flac(self, filename, track):
        """Embed vorbis comments in FLAC"""
        try:
            audio = FLAC(filename)
            
            audio['title'] = [track['title']]
            audio['artist'] = [self.artist]
            audio['album'] = [self.album]
            audio['date'] = [self.metadata['date']]
            audio['tracknumber'] = [str(track['number'])]
            
            # Embed cover art if available
            if self.metadata.get('cover_art_url'):
                picture = Picture()
                picture.type = 3  # Front cover
                with open(self.metadata['cover_art_url'], 'rb') as f:
                    picture.data = f.read()
                picture.mime = 'image/jpeg'
                audio.add_picture(picture)
            
            audio.save()
        except Exception as e:
            print(f"  ⚠️  Error tagging {filename}: {e}")
    
    def sanitize_filename(self, filename):
        """Remove invalid characters from filename for Windows"""
        # Remove invalid characters: < > : " / \ | ? *
        invalid_chars = r'<>:"/\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '-')
        # Replace multiple spaces/dashes with single
        filename = ' '.join(filename.split())
        return filename.strip()
        """Remove temporary files"""
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
            print("\n🧹 Cleaned up temporary files")
        except Exception as e:
            print(f"⚠️  Could not clean temp directory: {e}")
    
    def run(self):
        """Execute full digitization workflow"""
        print("=" * 60)
        print("🎙️  VINYL DIGITIZER")
        print("=" * 60)
        
        if not os.path.exists(self.input_file):
            print(f"❌ Input file not found: {self.input_file}")
            return False
        
        # Step 1: Search MusicBrainz
        if not self.search_musicbrainz():
            print("\n⚠️  Continuing without metadata (manual splitting won't work)")
            # Could add manual mode here in future
            return False
        
        # Step 1.5: Auto-limit tracks to what fits in the recording
        self.limit_tracks_to_recording()
        
        # Step 2: Split audio
        if not self.split_audio():
            return False
        
        # Step 3: Convert and tag
        if not self.convert_and_tag():
            return False
        
        # Step 4: Cleanup
        self.cleanup()
        
        print("\n" + "=" * 60)
        print("✅ COMPLETE!")
        print(f"📁 Output: {self.output_dir}")
        print("=" * 60)
        return True


def main():
    if len(sys.argv) < 3:
        print("Usage: python vinyl_digitizer.py <input.wav> <artist|release-id> [album] [mp3|flac]")
        print("\nMethods:")
        print("  1. Search by Artist/Album (slower, may fail on spelling):")
        print("     python vinyl_digitizer.py my_record.wav \"Pink Floyd\" \"The Wall\" mp3")
        print("\n  2. Direct Release ID (faster, more reliable):")
        print("     python vinyl_digitizer.py my_record.wav a9f37814-50c6-4efb-95f2-b8963ad43d08 mp3")
        print("\nTo find Release ID: Go to https://musicbrainz.org/, search album,")
        print("then copy the ID from the URL (the long code after /release/)")
        sys.exit(1)
    
    input_file = sys.argv[1]
    artist_or_id = sys.argv[2]
    album = sys.argv[3] if len(sys.argv) > 3 else ""
    
    # Determine output format (last argument if it's mp3 or flac)
    output_format = 'mp3'
    for arg in sys.argv[3:]:
        if arg.lower() in ['mp3', 'flac']:
            output_format = arg.lower()
            break
    
    digitizer = VinylDigitizer(input_file, artist_or_id, album, output_format)
    success = digitizer.run()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
