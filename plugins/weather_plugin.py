"""
ALEX — Weather Plugin
Get current weather information using OpenWeatherMap API.
"""

import requests

from plugins.plugin_loader import PluginBase
from utils.logger import log
import config


class WeatherPlugin(PluginBase):
    """Get weather information for a city."""

    name = "weather"
    description = "Get current weather conditions for any city"
    actions = ["get_weather"]

    def __init__(self):
        self.api_key = config.OPENWEATHER_API_KEY
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"

    def execute(self, params: dict) -> str:
        """
        Get weather for a city.

        Params:
            city: City name (e.g., 'London', 'New York', 'auto')
        """
        city = params.get("city", "auto")

        if not self.api_key or self.api_key == "your_openweather_key_here":
            return (
                "Weather plugin needs an API key. "
                "Get a free key at https://openweathermap.org/api and add it to your .env file "
                "as OPENWEATHER_API_KEY."
            )

        if city == "auto":
            # Try to get city from IP geolocation
            try:
                geo = requests.get("https://ipapi.co/json/", timeout=5).json()
                city = geo.get("city", "London")
            except Exception:
                city = "London"

        try:
            response = requests.get(
                self.base_url,
                params={
                    "q": city,
                    "appid": self.api_key,
                    "units": "metric",
                },
                timeout=10,
            )
            data = response.json()

            if response.status_code != 200:
                return f"Could not get weather for {city}: {data.get('message', 'Unknown error')}"

            temp = data["main"]["temp"]
            feels_like = data["main"]["feels_like"]
            humidity = data["main"]["humidity"]
            description = data["weather"][0]["description"]
            wind_speed = data["wind"]["speed"]

            return (
                f"Weather in {city}: {description}. "
                f"Temperature is {temp:.0f}°C, feels like {feels_like:.0f}°C. "
                f"Humidity is {humidity}% and wind speed is {wind_speed} meters per second."
            )

        except requests.Timeout:
            return "Weather request timed out. Please try again."
        except Exception as e:
            return f"Error getting weather: {e}"
