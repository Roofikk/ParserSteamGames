import requests
import asyncio
import aiohttp
import json
from bs4 import BeautifulSoup
from tqdm import tqdm
import os
from datetime import datetime
import uuid
import logging
import argparse


# args setting
parser = argparse.ArgumentParser(description='Steam Parser', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('-a', '--above', type=int, help='The upper limit of the parsing list, default: max')
parser.add_argument('-b', '--below', type=int, help='The lower limit of the parsing list, default: 0')
parser.add_argument('-q', '--quantity-write', type=int,
                    help='Which quantity parsing entry for writing json file, default: 1000')
parser.add_argument('-f', '--file', action='store_true',
                    help='Flag for getting the entries from the last parsing json file, default: takes from url request')
args = parser.parse_args()
config = vars(args)

# output setting
current_dir = os.path.join(os.getcwd(), 'outputs')
now = datetime.now().strftime('%d-%m-%Y %H-%M-%S')
path_dir_games = os.path.join(current_dir, now, 'successful')
path_dir_failed_games = os.path.join(current_dir, now, 'failed')

os.makedirs(path_dir_games)
os.makedirs(path_dir_failed_games)

# logging setting
logging.basicConfig(filename=f'logs-{now}.log', encoding='utf-8',
                    format='%(asctime)s.%(msecs)03d %(message)s', datefmt='%d-%m-%Y %H:%M:%S', level=logging.DEBUG)

def get_all_games():
    games_url = "https://api.steampowered.com/ISteamApps/GetAppList/v2?format=json"
    response_json = requests.get(games_url).json()
    return response_json["applist"]["apps"]


def format_game_data(game_id, response):
    if response is None:
        logging.info(f"Couldn't get game info by id: {game_id}")
        return {game_id: {'success': False, 'reason': 'unknown'}}

    game_json = dict(response[game_id])

    if "success" in game_json.keys():
        if game_json["success"] == False:
            return {game_id: {'success': False, 'reason': game_json.get('reason', 'unknown')}}

    game_data = dict(game_json.get('data'))

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
        'website': game_data.get('website', ''),
        'header_image_uri': game_data.get('header_image', ''),
        'screenshots': game_data.get('screenshots', []),
        # надо еще сделать проверку платформы
        # ---------
    }}

    # get release date
    release_date = game_data.get('release_date', {})
    my_data[game_id]['release_date'] = ''
    if release_date != '':
        date = dict(release_date).get('date', '')
        my_data[game_id]['release_date'] = date

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
        # items = []
        # items = [li.text.strip() for li in lis]

        reqs[req] = {}

        os_bit_version = lis[0].text

        if len(os_bit_version.split(':')) < 2:
            reqs[req]['os_bit_version'] = lis.pop(0).text

        for li in lis:
            li_split = li.text.split(':')

            if len(li_split) < 2:
                print(f'Check system requirements in game id: {game_id}')
                continue

            key = li_split[0].replace('*', '').strip()
            reqs[req][key] = li_split[1].strip()

        # reqs[req] = items

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
                    logging.warning("Too many requests")
                    return {game_id: {'success': False, 'reason': 'too many requests'}}

                text = await response.text()

                if response.status == 200:
                    return format_game_data(game_id, json.loads(text))
                else:
                    message = (f'Try getting game: {game_id}\n'
                               f'Bad request with status code: {response.status}\n'
                               f'Response text: {text}')
                    logging.error(message)
                    return {game_id: {'success': False, 'reason': message}}
    except asyncio.TimeoutError as e:
        logging.warning(f"TimeoutError on game_id: {game_id}")
        return {game_id: {'success': False, 'reason': 'timeout error'}}


# оптимальное количество запросов в секунду ~ 0.72-0,75 req/s
# насколько я понял, рефреш запросов происходит каждые 8 минут, но я могу ошибаться.
# по расчетам получается можно выполнить за раз сразу ~350 запросов и потом уйти на 8-ми минутный перекур
# такое я не проверял...
async def write_games_info(games: list, below: int, above: int, quantity_write: int):
    if above <= below:
        message = '"above" value cannot be less or equal "below"'
        logging.error(message)
        raise Exception(message)

    if below >= len(games):
        message = '"below" value cannot be greater than games amount'
        logging.error(message)
        raise Exception(message)

    if quantity_write <= 0:
        message = '"quantity_write" value cannot be less or equal zero. Recommended value gather 500'
        logging.error(message)
        raise Exception(message)

    games_format_data_dict = {}
    failed_games_dict = {}

    game_counter = 0

    for index in tqdm(range(below, above), bar_format='{l_bar}{bar:50}{r_bar}{bar:-10b}'):
        game_id = str(games[index]["appid"])
        logging.debug(f'Getting game: {game_id}')
        response = await get_game_data(game_id)
        await asyncio.sleep(1)
        game_counter += 1

        if response[game_id]['success']:
            games_format_data_dict.update(response)
        else:
            failed_games_dict.update(response)

        if game_counter >= quantity_write:
            write_json_file(games_format_data_dict, os.path.join(path_dir_games, str(uuid.uuid4()) + '.json'))
            games_format_data_dict.clear()

            write_json_file(failed_games_dict, os.path.join(path_dir_failed_games, str(uuid.uuid4()) + '.json'))
            failed_games_dict.clear()

            game_counter = 0

    # for task in tqdm(tasks):
    #     running_tasks.append(task)
    #     task_counter += 1
    #     game_counter += 1
    #
    #     if task_counter >= 4:
    #         response_games = await asyncio.gather(*running_tasks, return_exceptions=True)
    #
    #         games_dict = {}
    #         for g in response_games:
    #             games_dict.update(g)
    #
    #         failed_games = {game_id: games_dict[game_id] for game_id in games_dict if games_dict[game_id]['success'] == False}
    #         failed_games_dict.update(failed_games)
    #
    #         success_games = {game_id: games_dict[game_id] for game_id in games_dict if games_dict[game_id]['success'] == True}
    #         games_format_data_dict.update(success_games)
    #
    #         await asyncio.sleep(5.55)
    #         running_tasks.clear()
    #         task_counter = 0
    #
    #     if game_counter >= quantity_write:
    #         write_json_file(games_format_data_dict, os.path.join(path_dir_games, str(uuid.uuid4()) + '.json'))
    #         games_format_data_dict.clear()
    #
    #         write_json_file(failed_games_dict, os.path.join(path_dir_failed_games, str(uuid.uuid4()) + '.json'))
    #         failed_games_dict.clear()
    #
    #         game_counter = 0

    if len(games_format_data_dict) > 0:
        write_json_file(games_format_data_dict, os.path.join(path_dir_games, str(uuid.uuid4()) + '.json'))

    if len(failed_games_dict) > 0:
        write_json_file(failed_games_dict, os.path.join(path_dir_failed_games, str(uuid.uuid4()) + '.json'))


# while not used
async def try_again_get_games(games: list):
    again_failed = []
    success_games = []

    for row_game in games:
        format_game = await get_game_data(row_game)
        await asyncio.sleep(0.65)

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


async def main():
    games = []

    if config['file']:
        games = get_json_file(os.path.join(current_dir, 'games.json'))
    else:
        games = get_all_games()
        write_json_file(games, os.path.join(current_dir, 'games.json'))

        games = [game for game in games if game['name'] != '']
        logging.debug(f"Found games amount: {len(games)}")

    b = config['below'] if config['below'] is not None else 0
    a = config['above'] if config['above'] is not None else len(games)
    q = config['quantity_write'] if config['quantity_write'] is not None else 1000

    await write_games_info(games, b, a, q)


if __name__ == "__main__":
    a = config['above']
    b = config['below']
    q = config['quantity_write']
    f = config['file']

    asyncio.run(main())
