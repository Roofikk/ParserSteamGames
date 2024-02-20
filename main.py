import requests
import asyncio
import aiohttp
import json
from bs4 import BeautifulSoup
from tqdm import tqdm
import os
from datetime import datetime
import uuid


current_dir = os.path.join(os.getcwd(), 'outputs')
now = datetime.now().strftime('%d-%m-%Y %H-%M-%S')
path_dir_games = os.path.join(current_dir, now, 'successful')
path_dir_failed_games = os.path.join(current_dir, now, 'failed')

os.makedirs(path_dir_games)
os.makedirs(path_dir_failed_games)


def get_all_games():
    games_url = "https://api.steampowered.com/ISteamApps/GetAppList/v2?format=json"
    response_json = requests.get(games_url).json()
    # soup = BeautifulSoup(response_json)
    return response_json["applist"]["apps"]


def format_game_data(game_id, response):
    if response is None:
        # print(f"Couldn't get game info by id: {game_id}")
        return {game_id: {'success': False, 'reason': 'unknown'}}

    # print(f"Getting app by id: {game_id}")

    json = dict(response[game_id])

    if "success" in json.keys():
        if json["success"] == False:
            return {game_id: {'success': False, 'reason': json.get('reason', 'unknown')}}

    game_data = dict(json.get('data'))

    # Проверка на тип приложения
    if game_data["type"] != "game":
        return {game_id: {'success': False, 'reason': 'is not game'}}

    # также нужна проверка на релизную игру

    if 'coming_soon' in game_data['release_date'].keys():
        if game_data['release_date']['coming_soon'] == True:
            return {game_id: {'success': False, 'reason': 'not released'}}

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


# оптимальное количество запросов в секунду = 0,75 req/s
# если я правильно понял
async def write_games_info(games: list, count_game_to_write_file: int):
    tasks = []
    games_format_data_dict = {}
    failed_games_dict = {}

    for game in games:
        game_id = str(game["appid"])
        tasks.append(get_game_data(game_id))

    game_counter = 0
    task_counter = 0
    running_tasks = []

    for task in tqdm(tasks):
        running_tasks.append(task)
        task_counter += 1
        game_counter += 1

        if task_counter >= 4:
            response_games = await asyncio.gather(*running_tasks, return_exceptions=True)

            games_dict = {}
            for g in response_games:
                games_dict.update(g)

            failed_games = {game_id: games_dict[game_id] for game_id in games_dict if games_dict[game_id]['success'] == False}
            failed_games_dict.update(failed_games)

            success_games = {game_id: games_dict[game_id] for game_id in games_dict if games_dict[game_id]['success'] == True}
            games_format_data_dict.update(success_games)

            await asyncio.sleep(5.6)
            running_tasks.clear()
            task_counter = 0

        if game_counter >= count_game_to_write_file:
            write_json_file(games_format_data_dict, os.path.join(path_dir_games, str(uuid.uuid4()) + '.json'))
            games_format_data_dict.clear()

            write_json_file(failed_games_dict, os.path.join(path_dir_failed_games, str(uuid.uuid4()) + '.json'))
            failed_games_dict.clear()

            game_counter = 0

async def try_again_get_games(path: str, games: list):
    again_failed = []
    success_games = []

    for row_game in games:
        format_game = await get_game_data(row_game)
        await asyncio.sleep(0.7)

        if format_game['success'] is False:
            again_failed.append(format_game)
        else:
            success_games.append(format_game)

    return {'successes': success_games, 'failed': again_failed}


def write_json_file(games_list: dict, path_file: str):
    with open(path_file, 'w', encoding='utf-8') as f:
        json.dump(games_list, f, ensure_ascii=False, indent=4)
        f.close()

def get_json_file(path_file: str):
    f = open(path_file, 'r', encoding='utf-8')
    json_data = json.load(f)
    f.close()

    return json_data


async def main(path_file=''):
    if path_file is None or path_file == '':
        games = get_all_games()
        write_json_file(games, os.path.join(current_dir, 'games.json'))
    else:
        get_json_file(os.path.join(current_dir, 'games.json'))

    non_empty_games = [game for game in games if game['name'] != '']
    print(f"Games amount: {len(non_empty_games)}")

    await write_games_info(non_empty_games, 100)


if __name__ == "__main__":
    asyncio.run(main())
