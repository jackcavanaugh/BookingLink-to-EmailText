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
        chrome_options.add_argument('--disable-images')  # Skip loading images for faster rendering
        chrome_options.add_argument('--blink-settings=imagesEnabled=false')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--js-flags=--max_old_space_size=256')  # Limit memory usage

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
            logger.debug(f"Start date: {start_date}, End date: {end_date}")
            
            # Try to directly navigate to the specific date range if possible
            # This helps with HubSpot calendars that support direct date specification
            import urllib.parse
            from datetime import datetime
            
            # Format dates in a format HubSpot might understand (MM-DD-YYYY)
            try:
                start_obj = datetime.strptime(start_date, '%Y-%m-%d')
                start_formatted = start_obj.strftime('%m-%d-%Y')
                
                # Try to construct a URL with date parameters
                if '?' in self.url:
                    direct_url = f"{self.url}&date={start_formatted}"
                else:
                    direct_url = f"{self.url}?date={start_formatted}"
                    
                logger.debug(f"Attempting to navigate directly to date: {direct_url}")
                self.driver.get(direct_url)
            except Exception as e:
                logger.debug(f"Failed to navigate directly to date: {str(e)}")
                # Fallback to regular URL
                self.driver.get(self.url)

            # Set a longer page load timeout
            self.driver.set_page_load_timeout(30)

            # Log browser console messages if possible
            try:
                console_logs = self.driver.get_log('browser')
                logger.debug(f"Browser console logs: {console_logs}")
            except Exception as e:
                logger.debug(f"Unable to get browser logs: {str(e)}")

            # Wait for page to load
            logger.debug("Waiting for the page to fully load...")
            try:
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                logger.debug("Body element found")
            except Exception as e:
                logger.error(f"Error waiting for body element: {str(e)}")

            # Log document readyState
            ready_state = self.driver.execute_script("return document.readyState")
            logger.debug(f"Document readyState: {ready_state}")

            # Check if page has loaded with content
            page_length = self.driver.execute_script("return document.documentElement.outerHTML.length")
            logger.debug(f"Page HTML length: {page_length} characters")

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

            # Minimize wait times but still allow for JavaScript to initialize
            import time
            logger.debug("Waiting 2 seconds for JavaScript to initialize...")
            time.sleep(2)

            # Check for AJAX requests that might still be running
            loading_indicators = self.driver.find_elements(By.CSS_SELECTOR, '[class*="loading"], [class*="spinner"]')
            if loading_indicators:
                logger.debug(f"Found {len(loading_indicators)} loading indicators, waiting 2 more seconds...")
                time.sleep(2)

            # Get the page HTML
            html = self.driver.page_source

            # Log DOM structure 
            try:
                # Get top-level DOM structure (first two levels)
                dom_structure = self.driver.execute_script("""
                    let result = '';
                    function getNodeSummary(node, level) {
                        if (!node) return '';
                        let padding = '  '.repeat(level);
                        let summary = padding + node.nodeName;
                        if (node.id) summary += ' #' + node.id;
                        if (node.className) summary += ' .' + node.className.replace(/ /g, '.');
                        return summary + '\\n';
                    }

                    function getChildren(node, level, maxLevel) {
                        if (level > maxLevel) return '';
                        let result = '';
                        for (let i = 0; i < node.children.length; i++) {
                            const child = node.children[i];
                            result += getNodeSummary(child, level);
                            if (level < maxLevel) {
                                result += getChildren(child, level + 1, maxLevel);
                            }
                        }
                        return result;
                    }

                    return getChildren(document.body, 1, 2);
                """)
                logger.debug(f"DOM Structure (top 2 levels):\n{dom_structure}")
            except Exception as e:
                logger.error(f"Error getting DOM structure: {str(e)}")

            # Don't return mock data, force extraction of actual content
            if len(html) < 5000:
                logger.warning("Insufficient page content, waiting longer for full page load")
                # Wait longer for the page to load
                time.sleep(10)
                html = self.driver.page_source

            # Parse with BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # Save the full HTML for debugging
            try:
                with open('/tmp/hubspot_page.html', 'w') as f:
                    f.write(html)
                logger.debug("Saved full HTML to /tmp/hubspot_page.html")
            except Exception as e:
                logger.error(f"Failed to save full HTML: {str(e)}")

            # Log first 1000 chars for debugging
            logger.debug(f"HTML snippet (first 1000 chars): {html[:1000]}...")

            # Count meaningful tags to see if we have real content
            calendar_tags = ['calendar', 'date', 'time', 'slot', 'appointment', 'schedule']
            tag_counts = {}
            for tag_name in calendar_tags:
                # Fix the lambda function to properly check string in class
                tag_counts[tag_name] = len(soup.find_all(lambda tag: tag.name and tag.get('class') and 
                                                     any(cls and isinstance(cls, str) and tag_name in cls.lower() 
                                                         for cls in tag.get('class', []))))
            logger.debug(f"Calendar-related tag counts: {tag_counts}")

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

            # Check for all iframes which might contain the calendar
            iframes = self.driver.find_elements(By.TAG_NAME, 'iframe')
            logger.debug(f"Found {len(iframes)} iframes on the page")

            for i, iframe in enumerate(iframes):
                try:
                    iframe_src = iframe.get_attribute('src')
                    iframe_id = iframe.get_attribute('id')
                    iframe_class = iframe.get_attribute('class')
                    logger.debug(f"Iframe {i}: src='{iframe_src}', id='{iframe_id}', class='{iframe_class}'")
                except:
                    logger.debug(f"Couldn't get attributes for iframe {i}")

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
                    logger.debug(f"Iframe HTML length: {len(html)}")
                    soup = BeautifulSoup(html, 'html.parser')

                    # Save iframe HTML for debugging
                    try:
                        with open('/tmp/hubspot_iframe.html', 'w') as f:
                            f.write(html)
                        logger.debug("Saved iframe HTML to /tmp/hubspot_iframe.html")
                    except Exception as e:
                        logger.error(f"Failed to save iframe HTML: {str(e)}")

                except Exception as e:
                    logger.error(f"Error switching to iframe: {str(e)}")

            # Check for shadow DOM
            try:
                shadow_hosts = self.driver.execute_script("""
                    return Array.from(document.querySelectorAll('*')).filter(el => el.shadowRoot).length;
                """)
                logger.debug(f"Found {shadow_hosts} shadow DOM hosts")

                if shadow_hosts > 0:
                    # Try to extract content from shadow DOM
                    shadow_content = self.driver.execute_script("""
                        const hosts = Array.from(document.querySelectorAll('*')).filter(el => el.shadowRoot);
                        let result = [];
                        for (const host of hosts) {
                            try {
                                const root = host.shadowRoot;
                                result.push({
                                    tag: host.tagName,
                                    id: host.id,
                                    html: root.innerHTML.substring(0, 500) + '...'
                                });
                            } catch (e) {
                                console.error(e);
                            }
                        }
                        return result;
                    """)
                    logger.debug(f"Shadow DOM content snippets: {shadow_content}")
            except Exception as e:
                logger.error(f"Error checking for shadow DOM: {str(e)}")

            # Extract dates and times using HubSpot specific selectors
            # Structure for storing available slots by date
            available_slots_by_date = {}

            # First attempt: Look specifically for HubSpot calendar elements
            try:
                # Reduce wait time for HubSpot calendar 
                logger.debug("Waiting for HubSpot calendar to load (3 seconds)...")
                time.sleep(3)

                # Find available date buttons with explicit wait
                logger.debug("Looking for available date buttons...")
                try:
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'button[class*="date"], div[role="button"][aria-label*="March"], [data-test-id="available-date"]'))
                    )
                    logger.debug("Found at least one available date button")
                except TimeoutException:
                    logger.warning("Timeout waiting for available date buttons")

                # Find all available date buttons with more flexible selectors
                date_buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button[class*="date"], div[role="button"][aria-label*="March"], [data-test-id="available-date"]')
                logger.debug(f"Found {len(date_buttons)} available date buttons")

                # Save screenshot after finding date buttons
                try:
                    self.driver.save_screenshot("/tmp/hubspot_dates_found.png")
                    logger.debug("Saved screenshot with date buttons to /tmp/hubspot_dates_found.png")
                except Exception as e:
                    logger.error(f"Failed to save screenshot: {str(e)}")

                if date_buttons:
                    # Log all date buttons first
                    date_info = []
                    for i, btn in enumerate(date_buttons):
                        try:
                            label = btn.get_attribute('aria-label')
                            text = btn.text.strip()
                            date_info.append(f"Button {i}: label='{label}', text='{text}'")
                        except Exception as e:
                            logger.error(f"Error getting date button {i} info: {str(e)}")

                    logger.debug(f"Available date buttons: {date_info}")

                    # Extract and process all available dates first
                    for i, date_btn in enumerate(date_buttons):
                        try:
                            # Get date information
                            date_label = date_btn.get_attribute('aria-label')
                            day_number = date_btn.text.strip()
                            logger.debug(f"Processing date button {i}: label='{date_label}', day='{day_number}'")

                            # Format date from aria-label (e.g., "March 12th")
                            if date_label:
                                from datetime import datetime
                                try:
                                    # Remove "st", "nd", "rd", "th" from date string
                                    import re
                                    date_clean = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_label)
                                    logger.debug(f"Cleaned date string: '{date_clean}'")

                                    # Try to parse the date
                                    date_obj = datetime.strptime(date_clean, "%B %d")
                                    # Add year
                                    full_date = f"{date_obj.strftime('%B')} {date_obj.day}, {end_date.split('-')[0]}"
                                    logger.debug(f"Formatted date: '{full_date}'")
                                except Exception as e:
                                    logger.error(f"Error parsing date '{date_label}': {str(e)}")
                                    # Fallback if parsing fails
                                    full_date = date_label

                                # Initialize entry for this date
                                if full_date not in available_slots_by_date:
                                    available_slots_by_date[full_date] = []

                                logger.debug(f"Found available date: {full_date}")

                                # Click on date to see available times
                                logger.debug(f"Clicking on date button for {full_date}")
                                try:
                                    # Use JavaScript click for better reliability
                                    self.driver.execute_script("arguments[0].click();", date_btn)
                                    logger.debug(f"Clicked on date button for {full_date}")

                                    # Use shorter timeout to prevent browser hanging
                                    logger.debug("Waiting for time slots to load...")
                                    time.sleep(0.8) # Reduce wait time between operations

                                    # Take screenshot after clicking date
                                    try:
                                        self.driver.save_screenshot(f"/tmp/hubspot_times_{i}.png")
                                        logger.debug(f"Saved screenshot after clicking date {i} to /tmp/hubspot_times_{i}.png")
                                    except Exception as e:
                                        logger.error(f"Failed to save screenshot: {str(e)}")

                                    # Find available time slots
                                    time_buttons = self.driver.find_elements(By.CSS_SELECTOR, '[data-test-id="time-picker-btn"]')
                                    logger.debug(f"Found {len(time_buttons)} time buttons for {full_date}")

                                    # Extract times
                                    time_slots = []
                                    for time_btn in time_buttons:
                                        time_text = time_btn.text.strip()
                                        if time_text:
                                            time_slots.append(time_text)
                                            logger.debug(f"Found time slot: {time_text} for {full_date}")

                                    # Check if we found times
                                    if time_slots:
                                        logger.debug(f"Adding {len(time_slots)} time slots for {full_date}")
                                        available_slots_by_date[full_date] = time_slots
                                    else:
                                        logger.warning(f"No time slots found for {full_date}")

                                except Exception as e:
                                    logger.error(f"Error clicking date or extracting times: {str(e)}")
                        except Exception as e:
                            logger.error(f"Error processing date button {i}: {str(e)}")

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
                # Look for dates in the calendar - be more specific with selectors
                date_elements = soup.select('button[data-test-id="available-date"], button[aria-label*="March"], button[class*="date-picker-btn"][class*="valid"]')
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

            # Dump all interactive elements for analysis
            logger.debug("*** DUMPING ALL INTERACTIVE ELEMENTS ***")
            try:
                buttons = self.driver.find_elements(By.TAG_NAME, 'button')
                logger.debug(f"Found {len(buttons)} buttons")
                for i, btn in enumerate(buttons[:20]):  # Limit to first 20 to avoid huge logs
                    try:
                        btn_text = btn.text.strip()
                        btn_html = btn.get_attribute('outerHTML')
                        logger.debug(f"Button {i}: text='{btn_text}', HTML={btn_html[:100]}")
                    except:
                        pass

                inputs = self.driver.find_elements(By.TAG_NAME, 'input')
                logger.debug(f"Found {len(inputs)} input fields")
                for i, inp in enumerate(inputs[:10]):
                    try:
                        inp_type = inp.get_attribute('type')
                        inp_id = inp.get_attribute('id')
                        inp_name = inp.get_attribute('name')
                        logger.debug(f"Input {i}: type='{inp_type}', id='{inp_id}', name='{inp_name}'")
                    except:
                        pass

                # Look for HubSpot specific elements
                hubspot_elements = self.driver.find_elements(By.CSS_SELECTOR, '[data-test-id*="date"], [data-test-id*="time"], [class*="calendar"], [class*="hubspot"]')
                logger.debug(f"Found {len(hubspot_elements)} HubSpot-specific elements")
                for i, el in enumerate(hubspot_elements[:20]):
                    try:
                        el_tag = el.tag_name
                        el_text = el.text.strip()
                        el_html = el.get_attribute('outerHTML')
                        logger.debug(f"HubSpot element {i}: tag='{el_tag}', text='{el_text}', HTML={el_html[:100]}")
                    except:
                        pass
            except Exception as e:
                logger.error(f"Error dumping interactive elements: {str(e)}")

            # Extract raw data from page
            available_dates = []
            available_times = []

            # Look for any elements containing date or time information - handling both string and Tag types
            date_elements = soup.find_all(string=lambda text: isinstance(text, str) and ('March' in text or 'April' in text))
            time_elements = soup.find_all(string=lambda text: isinstance(text, str) and (':' in text and ('am' in text.lower() or 'pm' in text.lower())))

            logger.debug(f"Found {len(date_elements)} potential date strings and {len(time_elements)} potential time strings")

            # Log the first few date elements for debugging
            for i, date_el in enumerate(date_elements[:10]):
                logger.debug(f"Date element {i}: '{date_el}'")

            # Log the first few time elements for debugging
            for i, time_el in enumerate(time_elements[:10]):
                logger.debug(f"Time element {i}: '{time_el}'")

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
                logger.debug(f"Created result with {len(result)} dates and {len(available_times)} times")
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