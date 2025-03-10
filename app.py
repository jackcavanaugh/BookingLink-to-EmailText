import os
import logging
from flask import Flask, render_template, request, jsonify
from scraper import scrape_calendar_availability
from urllib.parse import urlparse
from selenium.common.exceptions import TimeoutException

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")

SUPPORTED_DOMAINS = [
    'calendly.com',
    'outlook.office365.com',
    'meetings.hubspot.com'
]

def is_valid_calendar_url(url):
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return any(supported in domain for supported in SUPPORTED_DOMAINS)
    except:
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/debug')
def debug():
    """Route for debugging application state"""
    import sys
    import platform
    import glob
    
    # Check for saved HTML files
    html_files = {}
    for path in glob.glob('/tmp/hubspot_*.html'):
        try:
            with open(path, 'r') as f:
                # Get file size and first 500 chars
                content = f.read(500)
                size = len(content)
                if os.path.getsize(path) > 500:
                    content += f"... (truncated, full size: {os.path.getsize(path)} bytes)"
                html_files[path] = {
                    'size': os.path.getsize(path),
                    'preview': content
                }
        except Exception as e:
            html_files[path] = {'error': str(e)}
    
    # Get last few lines from logging
    last_logs = []
    try:
        import subprocess
        result = subprocess.run(['tail', '-n', '50', '/tmp/app.log'], capture_output=True, text=True)
        if result.returncode == 0:
            last_logs = result.stdout.splitlines()
    except:
        last_logs = ["Couldn't retrieve logs"]
    
    debug_info = {
        'python_version': sys.version,
        'platform': platform.platform(),
        'supported_domains': SUPPORTED_DOMAINS,
        'environment': {k: v for k, v in os.environ.items() if not k.startswith('_') and k.isupper()},
        'saved_html_files': html_files,
        'last_logs': last_logs
    }
    
    return jsonify(debug_info)

@app.route('/scrape', methods=['POST'])
def scrape():
    try:
        logger.debug("Received scrape request")
        url = request.form.get('url', '').strip()
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        
        logger.debug(f"Request parameters - URL: {url}, Start: {start_date}, End: {end_date}")

        if not url or not start_date or not end_date:
            return jsonify({
                'error': 'Please provide all required fields'
            }), 400

        if not is_valid_calendar_url(url):
            return jsonify({
                'error': 'Invalid calendar URL. Supported platforms: Calendly, Outlook, HubSpot'
            }), 400

        try:
            # Set a timeout for the entire operation
            import threading
            import time
            
            result = {"availability": None, "error": None}
            
            def scrape_with_timeout():
                try:
                    result["availability"] = scrape_calendar_availability(url, start_date, end_date)
                except Exception as e:
                    result["error"] = str(e)
            
            # Start scraping in a separate thread
            scrape_thread = threading.Thread(target=scrape_with_timeout)
            scrape_thread.start()
            
            # Wait for the thread to complete with a timeout
            scrape_thread.join(timeout=30)  # 30 second timeout to prevent worker timeouts
            
            if scrape_thread.is_alive():
                # Timeout occurred
                logger.error("Scraping operation timed out")
                return jsonify({
                    'error': 'The operation timed out. HubSpot calendars can be slow to respond.'
                }), 504
            
            if result["error"]:
                logger.error(f"Error during scraping: {result['error']}")
                return jsonify({
                    'error': f"Error extracting real calendar data: {result['error']}"
                }), 500
                
            availability = result["availability"]
            
            if not availability:
                return jsonify({
                    'error': 'No available time slots found in the selected date range'
                }), 404
                
            # Check if the data might be mock data
            if len(availability) == 3 and all(slot.get('times') and len(slot.get('times')) == 5 and '9:00 AM' in slot.get('times', []) for slot in availability):
                return jsonify({
                    'error': 'Detected mock data pattern. Unable to extract real calendar data.'
                }), 500

            # Validate availability format before returning
            if isinstance(availability, list):
                return jsonify({
                    'success': True,
                    'availability': availability
                })
            else:
                logger.error(f"Invalid availability format: {type(availability)}")
                return jsonify({
                    'error': 'The calendar data could not be properly formatted'
                }), 500

        except RuntimeError as e:
            logger.error(f"Runtime error during scraping: {str(e)}")
            return jsonify({
                'error': str(e)
            }), 500
        except TimeoutException:
            return jsonify({
                'error': 'The calendar page took too long to load. Please try again.'
            }), 504
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return jsonify({
                'error': 'An unexpected error occurred while fetching calendar data. Please try again later.'
            }), 500

    except Exception as e:
        logger.error(f"Error in route handler: {str(e)}")
        return jsonify({
            'error': 'An unexpected error occurred. Please try again later.'
        }), 500