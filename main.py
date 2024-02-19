import requests
import asyncio
import aiohttp
import json
from bs4 import BeautifulSoup


def get_all_games():
    games_url = "https://api.steampowered.com/ISteamApps/GetAppList/v2?format=json"
    response_json = requests.get(games_url).json()
    # soup = BeautifulSoup(response_json)
    return response_json["applist"]["apps"]


async def get_game_info(game_id: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://store.steampowered.com/api/appdetails?appids={game_id}") as resp:
            text = await resp.text()
            return json.loads(text)


async def get_games_info(games: dict):
    games_list = []

    for game in games:
        id = str(game["appid"])
        response = await get_game_info(id)
        print(f"Getting app by id: {id}")

        await asyncio.sleep(0.2)

        json = response[id]

        if "success" in json.keys():
            if json["success"] == False:
                continue

        game_data = json["data"]

        if game_data["type"] != "game":
            continue

        my_data = {
            "steamid": game_data["steam_appid"],
            "name": game_data["name"],
            "description": game_data["short_description"],
            "languages": game_data["supported_languages"],
            # разработчики идут списков от 0
            "developers": game_data["developers"],
            # издатели идут так же списком
            "publishers": game_data["publishers"],
            # надо еще сделать проверку платформы
            # ---------
            # жанры надо тоже распарсить в нормальный список.
            "genres": game_data["genres"]
        }

        # parse HTML data requirements
        reqs = {}
        for req in game_data["pc_requirements"]:
            soup = BeautifulSoup(game_data["pc_requirements"][req])
            bb_ul = soup.find("ul", class_="bb_ul")
            lis = bb_ul.find_all("li")
            items = [li.text.strip() for li in lis]
            reqs[req] = items

        my_data["requirements"] = reqs

        games_list.append(my_data)

    return games_list


if __name__ == "__main__":
    games = get_all_games()
    print(f"Games amount: {len(games)}")

    loop = asyncio.new_event_loop()
    loop.set_debug(True)
    result = loop.run_until_complete(get_games_info(games))
    loop.close()

    # write games info in json file
