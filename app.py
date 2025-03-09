import os
import logging
from flask import Flask, render_template, request, jsonify
from scraper import scrape_calendar_availability
from urllib.parse import urlparse

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

@app.route('/scrape', methods=['POST'])
def scrape():
    try:
        url = request.form.get('url', '').strip()
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        if not url or not start_date or not end_date:
            return jsonify({
                'error': 'Please provide all required fields'
            }), 400

        if not is_valid_calendar_url(url):
            return jsonify({
                'error': 'Invalid calendar URL. Supported platforms: Calendly, Outlook, HubSpot'
            }), 400

        try:
            availability = scrape_calendar_availability(url, start_date, end_date)

            if not availability:
                return jsonify({
                    'error': 'No available time slots found in the selected date range'
                }), 404

            return jsonify({
                'success': True,
                'availability': availability
            })

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