import logging
from queue import Queue
from threading import Lock
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
import time

logger = logging.getLogger(__name__)

class WebDriverPool:
    def __init__(self, pool_size=3, max_retries=3):
        self.pool_size = pool_size
        self.max_retries = max_retries
        self.pool = Queue(maxsize=pool_size)
        self.lock = Lock()
        self._initialize_pool()

    def _create_driver(self):
        """Create a new Chrome WebDriver instance with optimized settings."""
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')  # Use new headless mode
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-images')
        chrome_options.add_argument('--blink-settings=imagesEnabled=false')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--js-flags=--max_old_space_size=256')
        # Additional options for better headless performance
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--disable-features=VizDisplayCompositor')
        chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')

        try:
            service = Service()
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(30)  # Set page load timeout
            return driver
        except Exception as e:
            logger.error(f"Failed to create WebDriver: {str(e)}")
            raise

    def _initialize_pool(self):
        """Initialize the pool with WebDriver instances."""
        for _ in range(self.pool_size):
            try:
                driver = self._create_driver()
                self.pool.put(driver)
            except Exception as e:
                logger.error(f"Failed to initialize WebDriver in pool: {str(e)}")

    def get_driver(self):
        """Get a WebDriver instance from the pool with retry logic."""
        for attempt in range(self.max_retries):
            try:
                driver = self.pool.get(timeout=5)  # Wait up to 5 seconds for a driver
                # Test if the driver is still responsive
                try:
                    driver.current_url
                    return driver
                except WebDriverException:
                    logger.warning("Retrieved unresponsive driver, creating new one")
                    self._cleanup_driver(driver)
                    driver = self._create_driver()
                    return driver
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} to get driver failed: {str(e)}")
                if attempt == self.max_retries - 1:
                    raise RuntimeError("Failed to get WebDriver after multiple attempts")
                time.sleep(1)  # Wait before retrying

    def return_driver(self, driver):
        """Return a WebDriver instance to the pool."""
        try:
            # Clear cookies and cache before returning to pool
            driver.delete_all_cookies()
            self.pool.put(driver, timeout=5)
        except Exception as e:
            logger.error(f"Failed to return driver to pool: {str(e)}")
            self._cleanup_driver(driver)

    def _cleanup_driver(self, driver):
        """Safely cleanup a WebDriver instance."""
        try:
            driver.quit()
        except Exception as e:
            logger.error(f"Error during driver cleanup: {str(e)}")

    def cleanup(self):
        """Cleanup all WebDriver instances in the pool."""
        while not self.pool.empty():
            try:
                driver = self.pool.get_nowait()
                self._cleanup_driver(driver)
            except Exception as e:
                logger.error(f"Error during pool cleanup: {str(e)}")

# Global pool instance
driver_pool = None

def get_driver_pool(pool_size=3):
    """Get or create the global driver pool instance."""
    global driver_pool
    if driver_pool is None:
        driver_pool = WebDriverPool(pool_size=pool_size)
    return driver_pool 