import logging
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import requests

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

    def scrape(self, start_date, end_date):
        try:
            if 'calendly.com' in self.domain:
                return self._scrape_calendly()
            elif 'outlook.office365.com' in self.domain:
                return self._scrape_outlook()
            elif 'meetings.hubspot.com' in self.domain:
                return self._scrape_hubspot(start_date, end_date)
            else:
                raise ValueError("Unsupported calendar platform")
        except Exception as e:
            logger.error(f"Error in scraper: {str(e)}")
            raise

    def _scrape_hubspot(self, start_date, end_date):
        if not self.driver:
            self.setup_driver()

        try:
            logger.debug(f"Loading HubSpot calendar page: {self.url}")
            logger.debug(f"Start date: {start_date}, End date: {end_date}")

            # Format the date and construct URL
            try:
                start_obj = datetime.strptime(start_date, '%Y-%m-%d')
                start_formatted = start_obj.strftime('%m-%d-%Y')
                direct_url = f"{self.url}&date={start_formatted}" if '?' in self.url else f"{self.url}?date={start_formatted}"
                logger.debug(f"Attempting to navigate to URL: {direct_url}")

                # Load the page
                self.driver.get(direct_url)

                # Log initial page state
                logger.debug("Initial page load complete.")
                logger.debug(f"Page title: {self.driver.title}")
                logger.debug(f"Current URL: {self.driver.current_url}")

                # Wait for body to be present and log initial HTML
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                initial_html = self.driver.page_source
                logger.debug(f"Initial HTML snippet (first 500 chars): {initial_html[:500]}")

                # Format target date strings
                target_month_day = start_obj.strftime('%B %-d')  # "March 10"
                target_month_day_suffix = start_obj.strftime('%B %-d') + self._get_day_suffix(start_obj.day)  # "March 10th"
                logger.info(f"Looking for exact match of: '{target_month_day}' or '{target_month_day_suffix}'")

                # Wait for calendar elements
                logger.debug("Waiting for calendar elements...")
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 
                    '[data-test-id="time-picker-btn"], [class*="calendar"], [class*="date-picker"]'))
                )
                logger.debug("Calendar elements found")

                # Find all date buttons first
                date_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                    'button[data-test-id="available-date"], button[class*="date"], [role="button"][aria-label*="March"], div[role="button"]')

                # Get and log all available dates first
                all_dates = []
                logger.info("\n=== Available Dates ===")
                for i, btn in enumerate(date_buttons):
                    try:
                        text = btn.text.strip()
                        label = btn.get_attribute('aria-label') or ''
                        if label or text:
                            all_dates.append(f"{label or text}")
                            logger.info(f"Found date: '{label or text}'")
                    except Exception as e:
                        logger.error(f"Error getting date button {i} details: {str(e)}")

                # Log what we're looking for
                logger.info(f"\nLooking for exact match of: '{target_month_day}' or '{target_month_day_suffix}'")

                # Now look for exact match only
                target_found = False
                for i, btn in enumerate(date_buttons):
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
                            target_found = True

                            # Click date and wait for times
                            self.driver.execute_script("arguments[0].click();", btn)
                            logger.info("Clicked matching date button")

                            # Extract times
                            time_buttons = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-test-id="time-picker-btn"]'))
                            )

                            times = []
                            for time_btn in time_buttons:
                                time_text = time_btn.text.strip()
                                if time_text:
                                    times.append(time_text)
                                    logger.info(f"Found time slot: {time_text}")

                            if times:
                                return [{
                                    'date': label or target_month_day,
                                    'times': times
                                }]
                            else:
                                error_msg = f"The date {target_month_day} is available but has no time slots. Please try another date."
                                logger.error(error_msg)
                                raise ValueError(error_msg)

                    except Exception as e:
                        logger.error(f"Error processing button {i}: {str(e)}")

                # If we get here, we didn't find the exact date
                available_dates_str = ', '.join(all_dates) if all_dates else 'No dates found'
                error_msg = f"The date {target_month_day} is not available for booking. Available dates are: {available_dates_str}"
                logger.error(error_msg)
                raise ValueError(error_msg)

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

    def _scrape_calendly(self):
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            times = soup.find_all('div', {'class': 'calendar-slot'})
            return self._format_times(times)
        except requests.RequestException as e:
            logger.error(f"Error scraping Calendly: {str(e)}")
            raise

    def _scrape_outlook(self):
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


def scrape_calendar_availability(url, start_date, end_date):
    scraper = CalendarScraper(url)
    try:
        logger.info(f"Starting calendar scraping for {url}")
        return scraper.scrape(start_date, end_date)
    except Exception as e:
        logger.error(f"Error in scraper: {str(e)}")
        raise