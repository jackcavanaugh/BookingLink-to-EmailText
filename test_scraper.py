import logging
from scraper import CalendarScraper
from datetime import datetime

# Configure logging for maximum detail
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_calendar_scraping():
    # Test URL and dates
    url = "https://meetings.hubspot.com/jack-cavanaugh?uuid=969061ca-161a-425a-a665-d1ed067eb681"
    start_date = "2025-03-10"
    end_date = "2025-03-10"
    timezone = "UTC"

    logger.info("Starting calendar scraping test")
    logger.info(f"URL: {url}")
    logger.info(f"Date range: {start_date} to {end_date}")

    scraper = None
    try:
        scraper = CalendarScraper(url)
        result = scraper.scrape(start_date, end_date, timezone)

        if result and 'slots' in result:
            slots = result['slots']
            logger.info("\n=== Time Slot Analysis ===")

            for slot in slots:
                logger.info(f"\nDate: {slot['date']}")
                logger.info("Available Times:")

                for time in slot['times']:
                    logger.info(f"\nRaw time string: '{time}'")
                    components = time.split(' ')

                    if len(components) < 2:
                        logger.error(f"Invalid time format - missing period: {time}")
                        logger.info(f"Components found: {components}")
                    else:
                        time_part = components[0]
                        period = components[1]
                        logger.info(f"Time: {time_part}")
                        logger.info(f"Period: {period}")

                        # Verify time format
                        try:
                            hour, minute = map(int, time_part.split(':'))
                            logger.info(f"Hour: {hour}, Minute: {minute}")
                            if period.upper() not in ['AM', 'PM']:
                                logger.error(f"Invalid period format: {period}")
                        except ValueError as e:
                            logger.error(f"Failed to parse time components: {e}")

    except Exception as e:
        logger.error(f"Error during testing: {str(e)}", exc_info=True)
    finally:
        if scraper and scraper.driver:
            scraper.cleanup_driver()

if __name__ == '__main__':
    test_calendar_scraping()