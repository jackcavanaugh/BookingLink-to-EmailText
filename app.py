import os
import logging
from flask import Flask, render_template, request, jsonify
from scraper import scrape_calendar_availability
from urllib.parse import urlparse
from selenium.common.exceptions import TimeoutException, WebDriverException
import json
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/app.log'),
        logging.StreamHandler()
    ]
)
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
        timezone = request.form.get('timezone', 'UTC')

        logger.debug(f"Request parameters - URL: {url}, Start: {start_date}, End: {end_date}, Timezone: {timezone}")

        if not url or not start_date or not end_date:
            return jsonify({
                'error': 'Please provide all required fields'
            }), 400

        if not is_valid_calendar_url(url):
            return jsonify({
                'error': 'Invalid calendar URL. Supported platforms: Calendly, Outlook, HubSpot'
            }), 400

        try:
            result = scrape_calendar_availability(url, start_date, end_date, timezone)
            availability = result.get('slots', [])
            increment_minutes = result.get('increment_minutes')
            errors = result.get('errors')
            partial_success = result.get('partial_success', False)

            if not availability and not partial_success:
                return jsonify({
                    'error': 'No available time slots found in the selected date range'
                }), 404

            # Prepare response data
            response_data = {
                'success': True,
                'availability': availability,
                'increment_minutes': increment_minutes
            }

            # Add timezone note if needed
            if not any(slot.get('timezone') for slot in availability):
                response_data['note'] = f'Times shown in {timezone}'

            # Add error information if there were partial failures
            if partial_success:
                response_data['partial_success'] = True
                response_data['errors'] = errors
                response_data['note'] = 'Some dates could not be processed. See errors for details.'

            return jsonify(response_data)

        except ValueError as e:
            logger.error(f"Validation error: {str(e)}")
            return jsonify({
                'error': str(e)
            }), 400
        except TimeoutException:
            return jsonify({
                'error': 'The calendar page took too long to load. Please try again.'
            }), 504
        except WebDriverException as e:
            logger.error(f"WebDriver error: {str(e)}")
            return jsonify({
                'error': 'There was a problem accessing the calendar. Please try again.'
            }), 503
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)