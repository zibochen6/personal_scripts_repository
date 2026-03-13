import os
import sys
import requests
import argparse
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

# Constants
API_BASE_URL = "https://api.pexels.com/videos"
DEFAULT_PER_PAGE = 80  # Max allowed by Pexels API per request

def get_api_key():
    """Get Pexels API key."""
    # API Key provided by user
    return "ydcuRcXB4hH4DDtIAHYSothgv13vQ7uPEDrMYnGMl6MvbrWghmLnCIgi"

def search_videos(api_key, query, total_count):
    """Search for videos and return a list of video objects."""
    videos = []
    page = 1
    headers = {"Authorization": api_key}
    
    print(f"Searching for '{query}'...")
    
    while len(videos) < total_count:
        per_page = min(DEFAULT_PER_PAGE, total_count - len(videos))
        params = {
            "query": query,
            "per_page": per_page,
            "page": page,
            "orientation": "landscape" # Default to landscape for better video usage usually
        }
        
        try:
            response = requests.get(f"{API_BASE_URL}/search", headers=headers, params=params, timeout=10)
            
            if response.status_code == 401:
                print("Error: Invalid API Key.")
                sys.exit(1)
            elif response.status_code == 429:
                print("Error: Rate limit exceeded.")
                sys.exit(1)
            elif response.status_code != 200:
                print(f"Error: API returned status code {response.status_code}")
                print(response.text)
                sys.exit(1)
                
            data = response.json()
            new_videos = data.get("videos", [])
            
            if not new_videos:
                print("No more videos found.")
                break
                
            videos.extend(new_videos)
            page += 1
            
        except Exception as e:
            print(f"An error occurred during search: {e}")
            sys.exit(1)
            
    return videos[:total_count]

def get_best_video_file(video_files):
    """Select the best quality video file from the list."""
    # Priority: HD quality, then highest width
    # Filter for mp4 format if possible
    mp4_files = [v for v in video_files if v.get("file_type") == "video/mp4"]
    files_to_check = mp4_files if mp4_files else video_files
    
    if not files_to_check:
        return None
        
    # Sort by width (resolution) descending
    files_to_check.sort(key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)
    return files_to_check[0]

def sanitize_filename(name):
    """Sanitize the filename to be safe for file systems."""
    return re.sub(r'[\\/*?:"<>|]', "", name)

def download_video(url, filepath):
    """Download a single video."""
    try:
        if os.path.exists(filepath):
            # Check if file size matches (optional, here just skipping if exists)
            # print(f"File {filepath} already exists. Skipping.")
            return True

        response = requests.get(url, stream=True, timeout=10)
        # total_size = int(response.headers.get('content-length', 0))
        block_size = 1024 # 1 Kibibyte
        
        with open(filepath, 'wb') as file:
            for data in response.iter_content(block_size):
                file.write(data)
        return True
    except Exception as e:
        print(f"Error downloading {filepath}: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return False

def main():
    parser = argparse.ArgumentParser(description="Download videos from Pexels based on keywords.")
    parser.add_argument("keyword", nargs="?", help="Keyword to search for")
    parser.add_argument("count", nargs="?", type=int, help="Number of videos to download")
    parser.add_argument("--api-key", help="Pexels API Key")
    
    args = parser.parse_args()
    
    # Handle inputs
    if args.api_key:
        os.environ["PEXELS_API_KEY"] = args.api_key
        
    api_key = get_api_key()
    
    keyword = args.keyword
    if not keyword:
        keyword = input("Enter keyword to search (e.g., nature): ").strip()
        
    count = args.count
    if not count:
        try:
            count = int(input("Enter number of videos to download (e.g., 5): ").strip())
        except ValueError:
            print("Invalid number. Defaulting to 5.")
            count = 5
            
    # Create download directory
    download_dir = os.path.join(os.getcwd(), f"{sanitize_filename(keyword)}_videos")
    os.makedirs(download_dir, exist_ok=True)
    print(f"Videos will be saved to: {download_dir}")
    
    # Search videos
    videos = search_videos(api_key, keyword, count)
    print(f"Found {len(videos)} videos. Starting download...")
    
    # Prepare download tasks
    download_tasks = []
    for video in videos:
        video_id = video.get("id")
        video_files = video.get("video_files", [])
        best_file = get_best_video_file(video_files)
        
        if best_file:
            link = best_file.get("link")
            ext = link.split(".")[-1].split("?")[0] # specific extension handling might be needed but usually link ends with .mp4
            if len(ext) > 4: ext = "mp4" # fallback
            
            filename = f"{video_id}.{ext}"
            filepath = os.path.join(download_dir, filename)
            download_tasks.append((link, filepath))
            
    # Download in parallel
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(download_video, link, path) for link, path in download_tasks]
        
        for future in tqdm(as_completed(futures), total=len(futures), desc="Total Progress"):
            pass
            
    print("\nAll downloads completed!")

if __name__ == "__main__":
    main()
