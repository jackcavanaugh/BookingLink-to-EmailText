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
                    # Format current date for URL
                    date_formatted = current_date.strftime('%m-%d-%Y')
                    target_month_day = current_date.strftime('%B %-d')  # "March 10"
                    target_month_day_suffix = target_month_day + self._get_day_suffix(current_date.day)  # "March 10th"

                    logger.info(f"\nChecking availability for: {target_month_day}")

                    # Construct query parameters
                    params = {
                        'date': date_formatted,
                        'timezone': timezone
                    }

                    # Add parameters to URL
                    if '?' in self.url:
                        direct_url = f"{self.url}&{urlencode(params)}"
                    else:
                        direct_url = f"{self.url}?{urlencode(params)}"

                    logger.debug(f"Attempting to navigate to URL: {direct_url}")

                    # Load the page
                    self.driver.get(direct_url)

                    # Wait for calendar elements
                    logger.debug("Waiting for calendar elements...")
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 
                        '[data-test-id="time-picker-btn"], [class*="calendar"], [class*="date-picker"]'))
                    )

                    # Find all date buttons
                    date_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                        'button[data-test-id="available-date"], button[class*="date"], [role="button"][aria-label*="March"], div[role="button"]')

                    # Now look for exact match only
                    target_found = False
                    for btn in date_buttons:
                        try:
                            text = btn.text.strip()
                            label = btn.get_attribute('aria-label') or ''

                            # Only accept if the full date string matches exactly
                            is_target = (
                                label.lower() == target_month_day.lower() or
                                label.lower() == target_month_day_suffix.lower()
                            )

                            if is_target:
                                logger.info(f"Found exact match for target date: {label}")

                                # Check if the button is enabled and clickable
                                is_disabled = (
                                    btn.get_attribute('disabled') == 'true' or
                                    btn.get_attribute('aria-disabled') == 'true' or
                                    'disabled' in (btn.get_attribute('class') or '')
                                )

                                if is_disabled:
                                    logger.warning(f"Date {target_month_day} is displayed but not available (disabled)")
                                    target_found = True  # Mark as found but skip processing
                                    break

                                # Try to click the button
                                try:
                                    self.driver.execute_script("arguments[0].click();", btn)
                                    logger.debug("Clicked matching date button")
                                except Exception as click_error:
                                    logger.warning(f"Date {target_month_day} is not clickable: {str(click_error)}")
                                    target_found = True  # Mark as found but skip processing
                                    break

                                # Wait for time slots to appear
                                try:
                                    time_buttons = WebDriverWait(self.driver, 5).until(
                                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-test-id="time-picker-btn"]'))
                                    )
                                except TimeoutException:
                                    logger.warning(f"No time slots appeared for {target_month_day} after clicking")
                                    target_found = True  # Mark as found but skip processing
                                    break

                                # Get increment if not already determined
                                if increment_minutes is None and len(time_buttons) >= 2:
                                    increment_minutes = self._get_time_increment(time_buttons)
                                    if increment_minutes:
                                        logger.info(f"Detected {increment_minutes}-minute increments between slots")

                                times = []
                                for time_btn in time_buttons:
                                    time_text = time_btn.text.strip()
                                    if time_text:
                                        # Convert time from GMT to target timezone
                                        converted_time = self._convert_time_to_timezone(time_text, timezone)
                                        times.append(converted_time)
                                        logger.info(f"Found time slot: {time_text} -> {converted_time} ({timezone})")

                                if times:
                                    all_available_slots.append({
                                        'date': label or target_month_day,
                                        'times': times,
                                        'timezone': timezone
                                    })
                                    logger.info(f"Added {len(times)} time slots for {target_month_day}")
                                target_found = True
                                break

                        except Exception as e:
                            logger.error(f"Error processing button: {str(e)}")

                    if not target_found:
                        logger.warning(f"Date {target_month_day} not found in calendar")

                except Exception as e:
                    logger.error(f"Error processing date {current_date.strftime('%Y-%m-%d')}: {str(e)}")

                # Move to next date
                current_date = current_date + timedelta(days=1)

            if not all_available_slots:
                error_msg = f"No available slots found between {start_date} and {end_date}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # Add increment information to the response
            return {
                'increment_minutes': increment_minutes,
                'slots': all_available_slots
            }

        except TimeoutException as e:
            logger.error(f"Timeout waiting for calendar elements: {str(e)}")
            raise TimeoutException(f"The calendar page took too long to load. Please try again.")
        except Exception as e:
            logger.error(f"Error during calendar extraction: {str(e)}")
            raise
        finally:
            try:
                self.driver.switch_to.default_content()
            except:
                pass

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

    def _extract_available_slots_from_html(self):
        """Fallback method to extract slots from HTML when selectors fail"""
        try:
            logger.debug("Attempting to extract slots directly from HTML")
            logger.debug(f"Current URL: {self.driver.current_url}")
            logger.debug(f"Page title: {self.driver.title}")
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            # Try to find dates and times using various patterns
            available_slots = []

            # Look for elements that might contain dates
            logger.debug("Attempting to extract date containers from HTML")
            # Simplify the lambda function to avoid syntax issues
            def class_filter(class_attr):
                if not class_attr:
                    return False
                if isinstance(class_attr, str):
                    return any(x in class_attr for x in ['date', 'day', 'calendar'])
                elif isinstance(class_attr, list):
                    return any(isinstance(cls, str) and any(x in cls for x in ['date', 'day', 'calendar']) for cls in class_attr)
                return False

            date_containers = soup.find_all(['div', 'button', 'td'], attrs={'class': class_filter})
            logger.debug(f"Found {len(date_containers)} potential date containers")

            # Extract text that looks like dates
            for i, container in enumerate(date_containers):
                try:
                    date_text = container.get_text().strip()
                    logger.debug(f"Container {i} text: '{date_text}'")

                    if date_text and len(date_text) > 1:  # Avoid empty or single-char results
                        # Simple check if it might be a date
                        if any(char.isdigit() for char in date_text):
                            logger.debug(f"Found potential date: {date_text}")
                            available_slots.append({
                                'date': date_text,
                                'times': ['Time information not available']
                            })
                except Exception as e:
                    logger.error(f"Error processing container {i}: {str(e)}")
                    continue

            if available_slots:
                logger.debug(f"Extracted {len(available_slots)} potential dates")
                return available_slots
            else:
                logger.debug("No dates found in fallback extraction")
                return [{'date': 'No dates found', 'times': ['No available times']}]

        except Exception as e:
            logger.error(f"Error in fallback extraction: {str(e)}")
            return [{'date': 'Error extracting dates', 'times': ['Error extracting times']}]

    def _create_mock_date_slots(self, start_date, end_date):
        """Create mock date slots for testing or when extraction fails"""
        logger.info("Generating mock calendar data")
        try:
            from datetime import datetime, timedelta

            # Parse start and end dates
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')

            # Generate dates between start and end
            mock_slots = []
            current = start
            while current <= end:
                date_str = current.strftime('%A, %B %d, %Y')
                # Generate some random times
                times = ['9:00 AM', '10:30 AM', '1:00 PM', '2:30 PM', '4:00 PM']

                mock_slots.append({
                    'date': date_str,
                    'times': times
                })

                current += timedelta(days=1)

            logger.debug(f"Generated {len(mock_slots)} mock date slots")
            return mock_slots
        except Exception as e:
            logger.error(f"Error generating mock data: {str(e)}")
            # Absolute fallback with hardcoded data
            return [
                {'date': 'Monday, March 10, 2025', 'times': ['9:00 AM', '2:00 PM']},
                {'date': 'Tuesday, March 11, 2025', 'times': ['10:00 AM', '3:00 PM']},
                {'date': 'Wednesday, March 12, 2025', 'times': ['11:00 AM', '4:00 PM']}
            ]


def scrape_calendar_availability(url, start_date, end_date, timezone='UTC'):
    scraper = CalendarScraper(url)
    try:
        logger.info(f"Starting calendar scraping for {url}")
        return scraper.scrape(start_date, end_date, timezone)
    except Exception as e:
        logger.error(f"Error in scraper: {str(e)}")
        raise