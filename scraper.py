import logging
import requests
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

        # Set the binary location to the Nix store path
        chrome_options.binary_location = "/nix/store/zi4f80l169xlmivz8vja8wlphq74qqk0-chromium-125.0.6422.141/bin/chromium"

        try:
            # Use system-installed ChromeDriver from Nix store
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
            self.driver.get(self.url)

            # Set a longer page load timeout
            self.driver.set_page_load_timeout(30)

            # Wait for page to load
            logger.debug("Waiting for the page to fully load...")
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Log debugging info
            logger.debug(f"Page title: {self.driver.title}")
            logger.debug(f"Current URL: {self.driver.current_url}")

            # Try saving a screenshot for debugging
            try:
                screenshot_path = "/tmp/calendar_screenshot.png"
                self.driver.save_screenshot(screenshot_path)
                logger.debug(f"Screenshot saved to {screenshot_path}")
            except Exception as e:
                logger.error(f"Failed to save screenshot: {str(e)}")

            # Instead of trying selectors, extract directly from HTML
            # because HubSpot uses complex dynamic structures
            logger.debug("Extracting calendar information directly from page...")

            # Give the page a bit more time to load JavaScript content
            import time
            time.sleep(5)

            # Get the page HTML
            html = self.driver.page_source

            # Don't return mock data, force extraction of actual content
            if len(html) < 5000:
                logger.warning("Insufficient page content, waiting longer for full page load")
                # Wait longer for the page to load
                time.sleep(10)
                html = self.driver.page_source

            # Parse with BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # Log first 1000 chars for debugging
            logger.debug(f"HTML snippet: {html[:1000]}...")

            # Test if the page contains calendar-related content
            calendar_keywords = ['calendar', 'schedule', 'appointment', 'booking', 'meeting']
            page_text = soup.get_text().lower()
            has_calendar_content = any(keyword in page_text for keyword in calendar_keywords)

            if not has_calendar_content:
                logger.warning("Page doesn't appear to contain calendar content, retrying with longer wait")
                # Wait longer for calendar content to load
                time.sleep(10)
                # Reload the page HTML
                html = self.driver.page_source
                soup = BeautifulSoup(html, 'html.parser')
                # Check again
                page_text = soup.get_text().lower()
                has_calendar_content = any(keyword in page_text for keyword in calendar_keywords)
                logger.debug(f"After additional wait, has_calendar_content: {has_calendar_content}")

            # Look for iframe which might contain the calendar
            iframe = soup.find('iframe')
            if iframe and iframe.get('src'):
                iframe_url = iframe.get('src')
                logger.debug(f"Found iframe with source: {iframe_url}")
                # Try switching to iframe
                try:
                    self.driver.switch_to.frame(0)  # switch to first iframe
                    logger.debug("Switched to iframe")
                    # Wait for iframe content to load
                    time.sleep(2)
                    html = self.driver.page_source
                    soup = BeautifulSoup(html, 'html.parser')
                except Exception as e:
                    logger.error(f"Error switching to iframe: {str(e)}")

            # Extract dates and times using HubSpot specific selectors
            # Structure for storing available slots by date
            available_slots_by_date = {}

            # First attempt: Look specifically for HubSpot calendar elements
            try:
                # Find available date buttons
                date_buttons = self.driver.find_elements(By.CSS_SELECTOR, '[data-test-id="available-date"]')
                logger.debug(f"Found {len(date_buttons)} available date buttons")

                if date_buttons:
                    # Extract and process all available dates first
                    for date_btn in date_buttons:
                        try:
                            date_label = date_btn.get_attribute('aria-label')
                            day_number = date_btn.text.strip()

                            # Format date from aria-label (e.g., "March 12th")
                            if date_label:
                                from datetime import datetime
                                try:
                                    # Remove "st", "nd", "rd", "th" from date string
                                    import re
                                    date_clean = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_label)
                                    # Try to parse the date
                                    date_obj = datetime.strptime(date_clean, "%B %d")
                                    # Add year
                                    full_date = f"{date_obj.strftime('%B')} {date_obj.day}, {end_date.split('-')[0]}"
                                except:
                                    # Fallback if parsing fails
                                    full_date = date_label

                                # Initialize entry for this date
                                if full_date not in available_slots_by_date:
                                    available_slots_by_date[full_date] = []

                                logger.debug(f"Found available date: {full_date}")

                                # Click on date to see available times
                                date_btn.click()
                                time.sleep(2)  # Wait for times to load

                                # Find available time slots
                                time_buttons = self.driver.find_elements(By.CSS_SELECTOR, '[data-test-id="time-picker-btn"]')
                                logger.debug(f"Found {len(time_buttons)} time buttons for {full_date}")

                                # Extract times
                                for time_btn in time_buttons:
                                    time_text = time_btn.text.strip()
                                    if time_text:
                                        available_slots_by_date[full_date].append(time_text)
                                        logger.debug(f"Found time slot: {time_text} for {full_date}")
                        except Exception as e:
                            logger.error(f"Error processing date button: {str(e)}")

                    # Convert to the expected format
                    available_slots = []
                    for date, times in available_slots_by_date.items():
                        available_slots.append({
                            'date': date,
                            'times': times if times else ['No specific times found']
                        })

                    if available_slots:
                        logger.debug(f"Successfully created {len(available_slots)} date slots with specific times")
                        return available_slots
            except Exception as e:
                logger.error(f"Error extracting dates and times directly: {str(e)}")

            # Second attempt: Parse directly from HTML with BeautifulSoup
            try:
                # Look for dates in the calendar
                date_elements = soup.select('[data-test-id="available-date"], [aria-label*="March"], [class*="date-picker-btn"][class*="valid"]')
                logger.debug(f"Found {len(date_elements)} potential date elements in HTML")

                # Time elements
                time_elements = soup.select('[data-test-id="time-picker-btn"], [class*="time-picker-btn"]')
                logger.debug(f"Found {len(time_elements)} potential time elements in HTML")

                # Extract dates from buttons
                for date_el in date_elements:
                    date_label = date_el.get('aria-label', '')
                    day_text = date_el.text.strip()

                    if date_label and 'March' in date_label:
                        # Format the date
                        date_text = f"March {day_text}, 2025"
                        if date_text not in available_slots_by_date:
                            available_slots_by_date[date_text] = []

                # If we found dates but no times in the first pass, extract times
                if available_slots_by_date:
                    # Extract times
                    for time_el in time_elements:
                        time_text = time_el.text.strip()
                        if time_text and ':' in time_text:
                            # Assign to all dates if we can't determine which date it belongs to
                            for date in available_slots_by_date.keys():
                                if time_text not in available_slots_by_date[date]:
                                    available_slots_by_date[date].append(time_text)

                # Convert to the expected format
                available_slots = []
                for date, times in available_slots_by_date.items():
                    available_slots.append({
                        'date': date,
                        'times': times if times else ['No specific times found']
                    })

                if available_slots:
                    logger.debug(f"Created {len(available_slots)} date slots from HTML parsing")
                    return available_slots
            except Exception as e:
                logger.error(f"Error in HTML parsing: {str(e)}")

            # If we get here, all direct extraction methods failed
            # Instead of returning mock data, try one more approach
            logger.warning("Direct extraction methods failed, trying alternative approach")
            
            # Extract raw data from page
            available_dates = []
            available_times = []
            
            # Look for any elements containing date or time information
            date_elements = soup.find_all(string=lambda text: text and ('March' in text or 'April' in text))
            time_elements = soup.find_all(string=lambda text: text and (':' in text and ('am' in text.lower() or 'pm' in text.lower())))
            
            logger.debug(f"Found {len(date_elements)} potential date strings and {len(time_elements)} potential time strings")
            
            # Process dates
            for date_el in date_elements:
                if 'March' in date_el and any(char.isdigit() for char in date_el):
                    available_dates.append(date_el.strip())
            
            # Process times
            for time_el in time_elements:
                if ':' in time_el and ('am' in time_el.lower() or 'pm' in time_el.lower()):
                    available_times.append(time_el.strip())
            
            # Create result structure
            if available_dates and available_times:
                result = []
                for date in available_dates[:3]:  # Limit to first 3 dates to avoid duplicates
                    result.append({
                        'date': date,
                        'times': available_times
                    })
                return result
            
            # If still no data, raise exception instead of returning mock data
            raise ValueError("Could not extract real calendar data. Refusing to return mock data.")

        except Exception as e:
            logger.error(f"Error scraping HubSpot calendar: {str(e)}")
            # Don't return mock data, raise the exception
            raise RuntimeError(f"Failed to extract real calendar data: {str(e)}")
        finally:
            # Make sure we return to the main frame if we switched to an iframe
            try:
                self.driver.switch_to.default_content()
            except:
                pass

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
            def class_filter(class_str):
                if not class_str:
                    return False
                return any(x in class_str for x in ['date', 'day', 'calendar'])

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