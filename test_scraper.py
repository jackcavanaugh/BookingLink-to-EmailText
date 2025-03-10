import logging
from scraper import CalendarScraper

# Configure logging for maximum detail
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test URL and dates
url = "https://meetings.hubspot.com/jack-cavanaugh?uuid=969061ca-161a-425a-a665-d1ed067eb681"
start_date = "2025-03-10"
end_date = "2025-03-10"

try:
    logger.info("Starting calendar scraping test")
    logger.info(f"URL: {url}")
    logger.info(f"Date range: {start_date} to {end_date}")

    scraper = CalendarScraper(url)
    available_slots = scraper.scrape(start_date, end_date)

    logger.info("\nExtracted available slots:")
    for slot in available_slots:
        logger.info(f"Date: {slot['date']}")
        logger.info(f"Times: {', '.join(slot['times'])}")
        logger.info("---")
except Exception as e:
    logger.error(f"Error during scraping: {str(e)}", exc_info=True)
finally:
    if 'scraper' in locals() and scraper.driver:
        scraper.cleanup_driver()