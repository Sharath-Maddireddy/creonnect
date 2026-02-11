"""
Instagram Scraper - DEMO STUB with Multiple Profiles

This is a temporary demo stub that returns hardcoded data
for various profiles to showcase the AI pipeline.

Replace with real scraping logic for production.
"""


# Demo data for multiple profiles
DEMO_PROFILES = {
    "_vaibhavkothari31": {
        "profile": {
            "username": "_vaibhavkothari31",
            "full_name": "Vaibhav Kothari",
            "bio": "21, vegetarian. Bangalore. Founder.",
            "followers": 79500,
            "following": 698,
            "total_posts": 230,
            "is_private": False,
        },
        "posts": [
            {
                "post_id": "1",
                "is_video": True,
                "likes": 1966,
                "comments": 19,
                "timestamp": 1706500000,
                "caption": "serious runner now!"
            },
            {
                "post_id": "2",
                "is_video": True,
                "likes": 6409,
                "comments": 31,
                "timestamp": 1706400000,
                "caption": "so fun."
            },
            {
                "post_id": "3",
                "is_video": True,
                "likes": 4072,
                "comments": 38,
                "timestamp": 1706300000,
                "caption": "make it happen."
            }
        ]
    },
    "ig_dhirendra": {
        "profile": {
            "username": "ig_dhirendra",
            "full_name": "Dhirendra",
            "bio": "Tech Enthusiast | Developer | Building cool stuff 🚀",
            "followers": 1200,
            "following": 420,
            "total_posts": 85,
            "is_private": False,
        },
        "posts": [
            {
                "post_id": "1",
                "is_video": True,
                "likes": 892,
                "comments": 45,
                "timestamp": 1706500000,
                "caption": "New project dropping soon! 🔥 #coding #tech"
            },
            {
                "post_id": "2",
                "is_video": False,
                "likes": 1250,
                "comments": 28,
                "timestamp": 1706400000,
                "caption": "Late night coding sessions hit different 💻"
            },
            {
                "post_id": "3",
                "is_video": True,
                "likes": 2100,
                "comments": 67,
                "timestamp": 1706300000,
                "caption": "Built this in a weekend! What do you think?"
            }
        ]
    },
    # Default fallback profile
    "default": {
        "profile": {
            "username": "demo_creator",
            "full_name": "Demo Creator",
            "bio": "Demo profile for testing the AI pipeline",
            "followers": 10000,
            "following": 500,
            "total_posts": 50,
            "is_private": False,
        },
        "posts": [
            {
                "post_id": "1",
                "is_video": True,
                "likes": 500,
                "comments": 25,
                "timestamp": 1706500000,
                "caption": "Demo post 1"
            },
            {
                "post_id": "2",
                "is_video": False,
                "likes": 750,
                "comments": 30,
                "timestamp": 1706400000,
                "caption": "Demo post 2"
            },
            {
                "post_id": "3",
                "is_video": True,
                "likes": 600,
                "comments": 20,
                "timestamp": 1706300000,
                "caption": "Demo post 3"
            }
        ]
    }
}


class InstagramPublicScraper:
    """Demo stub scraper that returns hardcoded sample data."""

    def scrape_profile(self, username: str) -> dict:
        """
        Returns demo data for the given username.
        Falls back to default profile if username not found.
        """

        if username in DEMO_PROFILES:
            data = DEMO_PROFILES[username]
            print(f"[DEMO] Using hardcoded data for: {username}")
        else:
            data = DEMO_PROFILES["default"].copy()
            data["profile"] = DEMO_PROFILES["default"]["profile"].copy()
            data["profile"]["username"] = username
            print(f"[DEMO] Username '{username}' not found, using default demo data")

        return data


