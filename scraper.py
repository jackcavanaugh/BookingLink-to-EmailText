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
                    "[data-test-id='meetings-frame']"
                ]

                for selector in selectors:
                    try:
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        logger.debug(f"Calendar loaded with selector: {selector}")
                        break
                    except TimeoutException:
                        continue
                else:
                    # Log the page source for debugging
                    logger.debug(f"Page source: {self.driver.page_source}")
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

def scrape_calendar_availability(url, start_date, end_date):
    scraper = CalendarScraper(url)
    try:
        logger.info(f"Starting calendar scraping for {url}")
        return scraper.scrape(start_date, end_date)
    except Exception as e:
        logger.error(f"Error in scraper: {str(e)}")
        raise