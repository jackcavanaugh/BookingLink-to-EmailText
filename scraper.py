import logging
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlencode
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import requests
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

class CalendarScraper:
    def __init__(self, url):
        self.url = url
        self.domain = urlparse(url).netloc.lower()
        self.driver = None

    def setup_driver(self):
        logger.debug("Setting up Chrome driver...")
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-images')
        chrome_options.add_argument('--blink-settings=imagesEnabled=false')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--js-flags=--max_old_space_size=256')

        chrome_options.binary_location = "/nix/store/zi4f80l169xlmivz8vja8wlphq74qqk0-chromium-125.0.6422.141/bin/chromium"

        try:
            service = Service('/nix/store/3qnxr5x6gw3k9a9i7d0akz0m6bksbwff-chromedriver-125.0.6422.141/bin/chromedriver')
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.debug("Chrome driver setup successful")
        except Exception as e:
            logger.error(f"Failed to setup Chrome driver: {str(e)}")
            raise RuntimeError(f"Failed to initialize browser: {str(e)}")

    def cleanup_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error cleaning up driver: {str(e)}")
            finally:
                self.driver = None

    def _convert_time_to_timezone(self, time_str, target_timezone):
        """Convert time from GMT to target timezone."""
        try:
            # Parse the time string (assuming it's in GMT)
            # HubSpot time format is typically like "5:45 pm"
            time_str = time_str.strip().lower()
            is_pm = 'pm' in time_str
            time_parts = time_str.replace('am', '').replace('pm', '').strip().split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1])

            # Convert to 24-hour format if PM
            if is_pm and hour != 12:
                hour += 12
            elif not is_pm and hour == 12:
                hour = 0

            # Create datetime object in GMT
            today = datetime.now().date()
            time_gmt = datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
            time_gmt = time_gmt.replace(tzinfo=ZoneInfo('GMT'))

            # Convert to target timezone
            time_local = time_gmt.astimezone(ZoneInfo(target_timezone))

            # Format in 12-hour clock
            return time_local.strftime('%-I:%M %p')

        except Exception as e:
            logger.error(f"Error converting time {time_str} to {target_timezone}: {str(e)}")
            return time_str  # Return original string if conversion fails

    def scrape(self, start_date, end_date, timezone='UTC'):
        try:
            if 'calendly.com' in self.domain:
                return self._scrape_calendly(timezone)
            elif 'outlook.office365.com' in self.domain:
                return self._scrape_outlook(timezone)
            elif 'meetings.hubspot.com' in self.domain:
                return self._scrape_hubspot(start_date, end_date, timezone)
            else:
                raise ValueError("Unsupported calendar platform")
        except Exception as e:
            logger.error(f"Error in scraper: {str(e)}")
            raise

    def _get_time_increment(self, time_slots):
        """Calculate the increment between time slots in minutes."""
        try:
            if len(time_slots) < 2:
                return None

            # Convert first two times to datetime objects for comparison
            time1 = time_slots[0].text.strip()
            time2 = time_slots[1].text.strip()

            # Parse times (assuming format like "5:45 pm")
            t1 = datetime.strptime(time1.lower(), "%I:%M %p")
            t2 = datetime.strptime(time2.lower(), "%I:%M %p")

            # Calculate difference in minutes
            diff = (t2 - t1).total_seconds() / 60
            return int(diff)
        except Exception as e:
            logger.error(f"Error calculating time increment: {str(e)}")
            return None

    def _scrape_hubspot(self, start_date, end_date, timezone='UTC'):
        if not self.driver:
            self.setup_driver()

        try:
            logger.debug(f"Loading HubSpot calendar page: {self.url}")
            logger.debug(f"Start date: {start_date}, End date: {end_date}, Timezone: {timezone}")

            # Parse start and end dates
            start_obj = datetime.strptime(start_date, '%Y-%m-%d')
            end_obj = datetime.strptime(end_date, '%Y-%m-%d')

            # Will store all available slots across dates
            all_available_slots = []
            increment_minutes = None

            # Loop through each date in the range
            current_date = start_obj
            while current_date <= end_obj:
                try:
                    # Format date for URL
                    date_formatted = current_date.strftime('%m-%d-%Y')
                    target_month_day = current_date.strftime('%B %-d')

                    logger.info(f"\nChecking availability for: {target_month_day}")

                    # Add parameters to URL
                    params = {
                        'date': date_formatted,
                        'timezone': timezone
                    }
                    direct_url = f"{self.url}{'&' if '?' in self.url else '?'}{urlencode(params)}"

                    logger.debug(f"Loading URL: {direct_url}")
                    self.driver.get(direct_url)

                    # Wait for calendar elements
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 
                        '[data-test-id="time-picker-btn"], [class*="calendar"], [class*="date-picker"]'))
                    )

                    # Find all date buttons
                    date_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                        'button[data-test-id="available-date"], button[class*="date"], [role="button"][aria-label*="March"]')

                    # Look for exact match
                    for btn in date_buttons:
                        text = btn.text.strip()
                        label = btn.get_attribute('aria-label') or ''

                        if label.lower() == target_month_day.lower():
                            logger.info(f"Found target date: {label}")

                            try:
                                self.driver.execute_script("arguments[0].click();", btn)
                                logger.debug("Clicked date button")

                                # Wait for and get time slots
                                time_buttons = WebDriverWait(self.driver, 5).until(
                                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-test-id="time-picker-btn"]'))
                                )

                                times = []
                                for time_btn in time_buttons:
                                    time_text = time_btn.text.strip()
                                    if time_text:
                                        logger.debug(f"Raw time from button: '{time_text}'")
                                        # Ensure time has AM/PM
                                        if ' ' not in time_text or not any(p in time_text.upper() for p in ['AM', 'PM']):
                                            logger.warning(f"Time missing period indicator: {time_text}")
                                            continue

                                        converted_time = self._convert_time_to_timezone(time_text, timezone)
                                        logger.debug(f"Converted time: '{converted_time}'")
                                        times.append(converted_time)

                                if times:
                                    all_available_slots.append({
                                        'date': label,
                                        'times': times,
                                        'timezone': timezone
                                    })
                                    logger.info(f"Added {len(times)} time slots for {target_month_day}")
                            except Exception as e:
                                logger.error(f"Error processing time slots: {str(e)}")
                            break

                except Exception as e:
                    logger.error(f"Error processing date {current_date}: {str(e)}")

                current_date += timedelta(days=1)

            if not all_available_slots:
                raise ValueError(f"No available slots found between {start_date} and {end_date}")

            return {
                'increment_minutes': increment_minutes,
                'slots': all_available_slots
            }

        except Exception as e:
            logger.error(f"Calendar extraction error: {str(e)}")
            raise

    def _get_time_increment(self, time_slots):
        """Calculate the increment between time slots in minutes."""
        try:
            if len(time_slots) < 2:
                return None

            # Convert first two times to datetime objects for comparison
            time1 = time_slots[0].text.strip()
            time2 = time_slots[1].text.strip()

            # Parse times (assuming format like "5:45 pm")
            t1 = datetime.strptime(time1.lower(), "%I:%M %p")
            t2 = datetime.strptime(time2.lower(), "%I:%M %p")

            # Calculate difference in minutes
            diff = (t2 - t1).total_seconds() / 60
            return int(diff)
        except Exception as e:
            logger.error(f"Error calculating time increment: {str(e)}")
            return None

    def _get_day_suffix(self, day):
        """Return the appropriate suffix for a day number (1st, 2nd, 3rd, etc.)"""
        if 10 <= day % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        return suffix

    def _scrape_calendly(self, timezone='UTC'):
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            times = soup.find_all('div', {'class': 'calendar-slot'})
            return self._format_times(times)
        except requests.RequestException as e:
            logger.error(f"Error scraping Calendly: {str(e)}")
            raise

    def _scrape_outlook(self, timezone='UTC'):
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            times = soup.find_all('div', {'class': 'time-slot'})
            return self._format_times(times)
        except requests.RequestException as e:
            logger.error(f"Error scraping Outlook: {str(e)}")
            raise

    def _format_times(self, times):
        return []

def scrape_calendar_availability(url, start_date, end_date, timezone='UTC'):
    scraper = CalendarScraper(url)
    try:
        logger.info(f"Starting calendar scraping for {url}")
        return scraper.scrape(start_date, end_date, timezone)
    except Exception as e:
        logger.error(f"Error in scraper: {str(e)}")
        raise