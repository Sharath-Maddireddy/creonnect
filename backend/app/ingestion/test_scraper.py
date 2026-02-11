from backend.app.ingestion.instagram_scraper import InstagramPublicScraper

scraper = InstagramPublicScraper()

data = scraper.scrape_profile("_vaibhavkothari31")

print(data["profile"])
print("Posts fetched:", len(data["posts"]))


