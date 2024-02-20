import requests
import asyncio
import aiohttp
import json
from bs4 import BeautifulSoup
from tqdm import tqdm

def get_all_games():
    games_url = "https://api.steampowered.com/ISteamApps/GetAppList/v2?format=json"
    response_json = requests.get(games_url).json()
    # soup = BeautifulSoup(response_json)
    return response_json["applist"]["apps"]


def format_game_data(game_id, response):
    if response is None:
        # print(f"Couldn't get game info by id: {game_id}")
        return {game_id: {'reason': 'unknown'}}

    # print(f"Getting app by id: {game_id}")

    json = dict(response[game_id])

    if "success" in json.keys():
        if json["success"] == False:
            return {game_id: {'reason': json.get('reason', 'unknown')}}

    game_data = dict(json.get('data'))

    # Проверка на тип приложения
    if game_data["type"] != "game":
        return {game_id: {'reason': 'is not game'}}

    # также нужна проверка на релизную игру

    if 'coming_soon' in game_data['release_date'].keys():
        if game_data['release_date']['coming_soon'] == True:
            return {game_id: {'reason': 'not released'}}

    my_data = {game_id: {
        "success": True,
        "steamid": game_data.get("steam_appid"),
        'age': game_data.get('required_age', 0),
        "name": game_data.get("name"),
        'short_description': game_data.get('short_description', ''),
        # здесь надо пройтись через bs. поскольку там разбросаны разные ссылки на видео и пр.
        'long_description': game_data.get('about_the_game', ''),
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
        'screenshots': game_data.get('screenshots', []),
        # надо еще сделать проверку платформы
        # ---------
    }}

    # get genres
    genres = [genre["description"] for genre in game_data.get('genres', [])]
    my_data[game_id]["genres"] = genres

    # get categories
    categories = [category['description'] for category in game_data.get('description', [])]
    my_data[game_id]['categories'] = categories

    # get movies
    movies = [{'name': movie['name'],
               # пока не знаю, за что отвечает значение "highlight"
               'highlight': movie['highlight'],
               'thumbnail': movie['thumbnail'],
               'webm': movie['webm'],
               'mp4': movie['mp4']} for movie in game_data.get('movies', [])]
    my_data[game_id]['movies'] = movies

    # parse HTML data requirements
    reqs = {}
    for req in game_data.get('pc_requirements', []):
        soup = BeautifulSoup(game_data["pc_requirements"][req], "html.parser")
        bb_ul = soup.find("ul", class_="bb_ul")
        lis = bb_ul.find_all("li")
        items = [li.text.strip() for li in lis]
        reqs[req] = items

    my_data[game_id]["requirements"] = reqs
    return my_data


async def get_game_data(game_id: str):
    session_timeout = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=5)
    try:
        async with aiohttp.ClientSession(timeout=session_timeout) as session:
            headers = {'Accept-Language': 'en-US'}
            async with session.get(f"https://store.steampowered.com/api/appdetails?appids={game_id}",
                                   allow_redirects=False, timeout=5, headers=headers) as response:
                if response.status == 429:
                    print("too many requests")
                    return {game_id: {'success': False, 'reason': 'too many requests'}}

                text = await response.text()
                return format_game_data(game_id, json.loads(text))
    except asyncio.TimeoutError as e:
        print(f"TimeoutError: {game_id}")
        return {game_id: {'success': False, 'reason': 'timeout error'}}


async def get_games_info(games: list):
    tasks = []
    games_format_data = []

    for game in games:
        id = str(game["appid"])
        tasks.append(get_game_data(id))

    # оптимальное количество запросов в секунду = 0,75 req/s
    # если я правильно понял
    counter = 0
    running_tasks = []
    for task in tqdm(tasks):
        running_tasks.append(task)
        counter += 1

        if counter >= 4:
            games_format_data.extend(await asyncio.gather(*running_tasks, return_exceptions=True))
            await asyncio.sleep(5.5)
            running_tasks.clear()
            counter = 0

    return games_format_data


if __name__ == "__main__":
    games = get_all_games()
    non_empty_games = [game for game in games if game['name'] != '']
    print(f"Games amount: {len(non_empty_games)}")

    loop = asyncio.new_event_loop()
    loop.set_debug(True)
    result = loop.run_until_complete(get_games_info(non_empty_games))
    loop.close()
