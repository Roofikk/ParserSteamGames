import requests
import asyncio
import aiohttp
import json
from bs4 import BeautifulSoup
from collections import defaultdict


def get_all_games():
    games_url = "https://api.steampowered.com/ISteamApps/GetAppList/v2?format=json"
    response_json = requests.get(games_url).json()
    # soup = BeautifulSoup(response_json)
    return response_json["applist"]["apps"]


sem = asyncio.Semaphore(10)

async def get_game_info(game_id: str):
    async with sem:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://store.steampowered.com/api/appdetails?appids={game_id}") as response:
                text = await response.text()
                return json.loads(text)


async def get_games_info(games: dict):
    games_list = []
    fail_games_list = []

    for game in games:
        id = str(game["appid"])
        response = await get_game_info(id)

        if response is None:
            print(f"Couldn't get game info by id: {id}")
            fail_games_list.append(id)

        print(f"Getting app by id: {id}")

        await asyncio.sleep(0.1)

        json = response[id]

        if "success" in json.keys():
            if json["success"] == False:
                continue

        game_data = dict(json["data"])

        # Проверка на тип приложения
        if game_data["type"] != "game":
            continue

        # также нужна проверка на релизную игру

        if 'coming_soon' in game_data['release_date'].keys():
            if game_data['release_date']['coming_soon'] == True:
                continue

        my_data = {
            "steamid": game_data.get("steam_appid"),
            'age': game_data.get('required_age', 0),
            "name": game_data.get("name"),
            "description": game_data.get("short_description", ""),
            # через запятую
            # если нужно, могу разбить в список
            "languages": game_data.get("supported_languages", ""),
            # разработчики идут списков от 0
            "developers": game_data.get("developers", []),
            # издатели идут так же списком
            "publishers": game_data.get("publishers", []),
            'release_date': game_data['release_date']['date'],
            'website': game_data['website'],
            'header_image_uri': game_data['header_image'],
            'screenshots': game_data['screenshots'],
            # надо еще сделать проверку платформы
            # ---------
        }

        # get genres
        genres = [genre["description"] for genre in game_data['genres']]
        my_data["genres"] = genres

        # get categories
        categories = [category['description'] for category in game_data['categories']]
        my_data['categories'] = categories

        # get movies
        movies = [{'name': movie['name'],
                   # пока не знаю, за что отвечает значение "highlight"
                   'highlight': movie['highlight'],
                   'thumbnail': movie['thumbnail'],
                   'webm': movie['webm'],
                   'mp4': movie['mp4']} for movie in game_data['movies']]
        my_data['movies'] = movies



        # parse HTML data requirements
        reqs = {}

        for req in game_data["pc_requirements"]:
            soup = BeautifulSoup(game_data["pc_requirements"][req], "html.parser")
            bb_ul = soup.find("ul", class_="bb_ul")
            lis = bb_ul.find_all("li")
            items = [li.text.strip() for li in lis]
            reqs[req] = items

        my_data["requirements"] = reqs

        games_list.append(my_data)

    return games_list, fail_games_list


if __name__ == "__main__":
    games = get_all_games()
    print(f"Games amount: {len(games)}")

    loop = asyncio.new_event_loop()
    loop.set_debug(True)
    result = loop.run_until_complete(get_games_info(games))
    loop.close()

    # write games info in json file
