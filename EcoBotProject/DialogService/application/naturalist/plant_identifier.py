import logging
import aiohttp
from utils.bot_messages import (
    PLANT_RESULT_GENUS, PLANT_RESULT_SPECIES, PLANT_RESULT_BEST_MATCH, PLANT_RESULT_PARSE_ERROR,
)

logger = logging.getLogger(__name__)

PLANTNET_URL = "https://my-api.plantnet.org/v2/identify/all"


async def identify_plant(image_bytes: bytes, plantnet_api_key: str, session: aiohttp.ClientSession) -> dict | None:
    params = {"api-key": plantnet_api_key}
    data = aiohttp.FormData()
    data.add_field("images", image_bytes, filename="plant.jpg", content_type="image/jpeg")

    try:
        async with session.post(PLANTNET_URL, params=params, data=data) as response:
            if response.status == 200:
                return await response.json()
            else:
                logger.error(f"PlantNet API error: {response.status} - {await response.text()}")
                return None
    except aiohttp.ClientError as e:
        logger.error(f"PlantNet HTTP request failed: {e}")
        return None


def format_plant_info(data: dict) -> str:
    try:
        best_match = data.get("bestMatch", "Неизвестно")
        if not best_match or best_match == "Неизвестно":
            results = data.get("results", [])
            if results:
                species_info = results[0].get("species", {})
                genus = species_info.get("genus", {}).get("scientificNameWithoutAuthor", "Неизвестно")
                family = species_info.get("family", {}).get("scientificNameWithoutAuthor", "Неизвестно")
                return PLANT_RESULT_GENUS.format(genus=genus, family=family)
        else:
            results = data.get("results", [])
            for result in results:
                if result.get("species", {}).get("scientificNameWithoutAuthor") in best_match:
                    species_info = result["species"]
                    genus = species_info.get("genus", {}).get("scientificNameWithoutAuthor", "Неизвестно")
                    family = species_info.get("family", {}).get("scientificNameWithoutAuthor", "Неизвестно")
                    return PLANT_RESULT_SPECIES.format(best_match=best_match, genus=genus, family=family)
            return PLANT_RESULT_BEST_MATCH.format(best_match=best_match)
    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Error parsing PlantNet response: {e}")
        return PLANT_RESULT_PARSE_ERROR
