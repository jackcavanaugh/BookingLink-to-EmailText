
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

            # Wait for initial calendar load with multiple possible selectors
            logger.debug("Waiting for calendar to load...")
            try:
                # Try multiple selectors that could indicate calendar is loaded
                selectors = [
                    ".DatePickerV2__StyledTable",
                    ".meetings-schedule",
                    ".meetings-frame-wrapper",
                    "[data-test-id='meetings-frame']",
                    ".private-calendar",
                    ".calendar-table",
                    "div[role='calendar']",
                    "table[role='grid']",
                    "div[class*='calendar']"
                ]

                # First log the URL we're actually on after navigation
                logger.debug(f"Current URL after navigation: {self.driver.current_url}")
                
                # Capture screenshot for debugging
                try:
                    screenshot_path = "/tmp/calendar_screenshot.png"
                    self.driver.save_screenshot(screenshot_path)
                    logger.debug(f"Screenshot saved to {screenshot_path}")
                except Exception as e:
                    logger.error(f"Failed to save screenshot: {str(e)}")
                
                for selector in selectors:
                    try:
                        WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        logger.debug(f"Calendar loaded with selector: {selector}")
                        break
                    except TimeoutException:
                        logger.debug(f"Selector not found: {selector}")
                        continue
                else:
                    # Try more generic selectors as fallback
                    try:
                        # Look for any button that might be a date selector
                        date_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                        if date_buttons:
                            logger.debug(f"Found {len(date_buttons)} buttons")
                            # Click the first visible button that might be a date
                            for btn in date_buttons:
                                if btn.is_displayed() and btn.is_enabled():
                                    btn.click()
                                    logger.debug("Clicked a potential date button")
                                    break
                            return self._extract_available_slots_from_html()
                    except Exception as e:
                        logger.error(f"Error in fallback selection: {str(e)}")
                    
                    # Log the page source for debugging
                    logger.debug(f"Page title: {self.driver.title}")
                    logger.debug(f"Page source snippet: {self.driver.page_source[:1000]}...")
                    raise TimeoutException("Could not find any calendar elements")

            except TimeoutException:
                logger.error("Timeout waiting for calendar to load")
                raise TimeoutException("The calendar page took too long to load. Please try again.")

            # Extract available time slots
            available_slots = []

            try:
                # Find available dates with various possible selectors
                date_selectors = [
                    "button[data-test-id='unavailable-date']:not([disabled])",
                    ".date-picker-btn:not(.disabled)",
                    "[data-selenium-test='day-button']"
                ]

                days = []
                for selector in date_selectors:
                    days = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if days:
                        logger.debug(f"Found {len(days)} available days with selector: {selector}")
                        break

                for day in days:
                    try:
                        # Get date text from button
                        date_text = day.get_attribute("aria-label") or day.text
                        if not date_text:
                            continue

                        logger.debug(f"Processing date: {date_text}")
                        day.click()

                        # Wait for time slots with multiple possible selectors
                        time_selectors = [
                            "button[data-test-id='time-button']",
                            ".time-picker-btn:not(.disabled)",
                            "[data-selenium-test='time-button']"
                        ]

                        for selector in time_selectors:
                            try:
                                WebDriverWait(self.driver, 5).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                                )
                                time_slots = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                times = [slot.text.strip() for slot in time_slots if slot.is_displayed() and slot.text.strip()]

                                if times:
                                    available_slots.append({
                                        'date': date_text,
                                        'times': times
                                    })
                                    logger.debug(f"Added {len(times)} time slots for {date_text}")
                                break
                            except TimeoutException:
                                continue

                    except Exception as e:
                        logger.error(f"Error processing day: {str(e)}")
                        continue

            except NoSuchElementException as e:
                logger.error(f"Could not find calendar elements: {str(e)}")
                raise RuntimeError(f"Failed to find calendar elements: {str(e)}")

            if not available_slots:
                logger.info("No available time slots found")

            return available_slots

        except Exception as e:
            logger.error(f"Error scraping HubSpot calendar: {str(e)}")
            raise RuntimeError(f"Failed to scrape calendar: {str(e)}")

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
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            # Try to find dates and times using various patterns
            available_slots = []
            
            # Look for elements that might contain dates
            date_containers = soup.find_all(['div', 'button', 'td'], 
                                           attrs={'class': lambda c: c and any(x in c for x in 
                                                                             ['date', 'day', 'calendar'])
                                                  if c else False})
            
            # Extract text that looks like dates
            for container in date_containers:
                date_text = container.get_text().strip()
                if date_text and len(date_text) > 1:  # Avoid empty or single-char results
                    # Simple check if it might be a date
                    if any(char.isdigit() for char in date_text):
                        available_slots.append({
                            'date': date_text,
                            'times': ['Time information not available']
                        })
            
            if available_slots:
                logger.debug(f"Extracted {len(available_slots)} potential dates")
                return available_slots
            else:
                logger.debug("No dates found in fallback extraction")
                return [{'date': 'No dates found', 'times': ['No available times']}]
        
        except Exception as e:
            logger.error(f"Error in fallback extraction: {str(e)}")
            return [{'date': 'Error extracting dates', 'times': ['Error extracting times']}]


def scrape_calendar_availability(url, start_date, end_date):
    scraper = CalendarScraper(url)
    try:
        logger.info(f"Starting calendar scraping for {url}")
        return scraper.scrape(start_date, end_date)
    except Exception as e:
        logger.error(f"Error in scraper: {str(e)}")
        raise
