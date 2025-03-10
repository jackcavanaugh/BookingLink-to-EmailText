import logging
from scraper import CalendarScraper
from datetime import datetime

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

    # Create scraper
    scraper = CalendarScraper(url)

    try:
        # Log the target date we're looking for
        target_date = datetime.strptime(start_date, '%Y-%m-%d')
        target_date_str = target_date.strftime('%B %-d')  # e.g., "March 10"
        logger.info(f"\nLooking for target date: {target_date_str}")

        # Attempt to scrape calendar data
        logger.info("\nAttempting to scrape calendar data...")
        available_slots = scraper.scrape(start_date, end_date)

        if available_slots:
            logger.info("\nExtracted available slots:")
            for slot in available_slots.get('slots', []):
                logger.info("-" * 50)
                logger.info(f"Date: {slot['date']}")
                logger.info("Times:")
                for time in slot['times']:
                    # Log each time slot with its components
                    time_parts = time.split(' ')
                    logger.info(f"  Raw time: {time}")
                    logger.info(f"  Components: Time={time_parts[0]}, Period={time_parts[1] if len(time_parts) > 1 else 'MISSING'}")
        else:
            logger.warning("No available slots were returned")

    except ValueError as ve:
        logger.error(f"Validation error: {str(ve)}")
    except Exception as e:
        logger.error(f"Error during scraping: {str(e)}", exc_info=True)

except Exception as e:
    logger.error(f"Error setting up scraper: {str(e)}", exc_info=True)
finally:
    if 'scraper' in locals() and scraper.driver:
        scraper.cleanup_driver()