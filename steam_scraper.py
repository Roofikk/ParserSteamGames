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
parser.add_argument('-f', '--file', type=str,
                    help='Path to any json file which was created on last parses. '
                         'The path can be either from the root of the program or the full path. '
                         'Default: takes from url request')
parser.add_argument('-r', '--repeat', action='store_true',
                    help='Flag for trying repeat parse games which could not be accessed at the moment of parsing, '
                         'default: flag is false')
args = parser.parse_args()
config = vars(args)

# output setting
now = datetime.now().strftime('%d-%m-%Y %H-%M-%S')
outputs_dir = os.path.join(os.getcwd(), 'outputs')
current_dir = os.path.join(outputs_dir, now)
path_dir_games = os.path.join(current_dir, 'successful')
path_dir_failed_games = os.path.join(current_dir, 'failed')

os.makedirs(path_dir_games)
os.makedirs(path_dir_failed_games)

# logging setting
dir_logs = os.path.join(current_dir, 'logs')
os.makedirs(dir_logs)

logging.basicConfig(filename=os.path.join(dir_logs, f'logs-{now}.log'), encoding='utf-8',
                    format='%(asctime)s.%(msecs)03d %(message)s', datefmt='%d-%m-%Y %H:%M:%S', level=logging.DEBUG)


def get_all_games():
    games_url = "https://api.steampowered.com/ISteamApps/GetAppList/v2?format=json"
    response_json = requests.get(games_url).json()
    return response_json["applist"]["apps"]


def format_game_data(game_id, response):
    logging.info(f'Formatting game: {game_id}')

    if response is None:
        logging.info(f"Couldn't get game info by id: {game_id}")
        return {'appid': game_id, 'success': False, 'reason': 'unknown'}

    game_json = dict(response[game_id])

    if "success" in game_json.keys():
        if not game_json["success"]:
            return {'appid': game_id, 'success': False, 'reason': game_json.get('reason', 'unknown')}

    game_data = dict(game_json.get('data', {}))

    # Проверка на тип приложения
    if game_data["type"] != "game":
        return {'appid': game_id, 'success': False, 'reason': 'is not game'}

    # также нужна проверка на релизную игру
    if 'coming_soon' in game_data['release_date'].keys():
        if game_data['release_date']['coming_soon']:
            return {'appid': game_id, 'success': False, 'reason': 'not released'}

    my_data = {game_id: {
        "success": True,
        "steamid": game_data.get("steam_appid"),
        'age': game_data.get('required_age', 0),
        "name": game_data.get("name"),
        'short_description': game_data.get('short_description', ''),
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
    }}

    # scrape description
    html_description = game_data.get('about_the_game', '')
    desc_text = get_description_text(html_description)

    # если надо будет только текст, то заменить на desc_text
    my_data['long_description'] = html_description

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
    categories = [category['description'] for category in game_data.get('categories', [])]
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
        bb_ul = soup.find("ul")
        lis = bb_ul.find_all("li")

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

    my_data[game_id]["requirements"] = reqs
    return my_data


def get_description_text(html):
    soup = BeautifulSoup(html, 'html.parser')

    if soup is not None:
        return soup.text
    else:
        return None


async def get_game_data(game_id: str):
    logging.info(f'Getting game: {game_id}')
    session_timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=10)
    try:
        async with aiohttp.ClientSession(timeout=session_timeout) as session:
            headers = {'Accept-Language': 'en-US'}
            async with session.get(f"https://store.steampowered.com/api/appdetails?appids={game_id}",
                                   allow_redirects=False, timeout=10, headers=headers) as response:
                if response.status == 429:
                    logging.warning(f"Too many requests: {game_id}")
                    return {'appid': game_id, 'success': False, 'reason': 'too many requests'}

                text = await response.text()

                if response.status == 200:
                    response_json = json.loads(text)
                    return format_game_data(game_id, response_json)
                else:
                    response_message = (f'Try getting game: {game_id}\n'
                                        f'Bad request with status code: {response.status}\n'
                                        f'Response text: {text}')
                    logging.error(response_message)
                    return {'appid': game_id, 'success': False, 'reason': response_message}
    except asyncio.TimeoutError as e:
        logging.warning(f"TimeoutError on game_id: {game_id}")
        return {'appid': game_id, 'success': False, 'reason': 'timeout error'}
    except json.JSONDecodeError as e:
        message_error = f'Failed to convert json file: {game_id}'
        logging.error(message_error)
        return {'appid': game_id, 'success': False, 'reason': message_error}


async def write_games_info(games: list, below: int, above: int, quantity_write: int):
    if above <= below:
        exception_message = '"above" value cannot be less or equal "below"'
        logging.error(exception_message)
        raise Exception(exception_message)

    if below >= len(games):
        exception_message = '"below" value cannot be greater than games amount'
        logging.error(exception_message)
        raise Exception(exception_message)

    if quantity_write <= 0:
        exception_message = '"quantity_write" value cannot be less or equal zero. Recommended value gather 500'
        logging.error(exception_message)
        raise Exception(exception_message)

    games_format_data_dict = {}
    failed_games_list = []

    game_counter = 0
    task_counter = 0
    tasks = []
    max_step = 10
    for index in tqdm(range(below, above), desc='main',
                      bar_format='{l_bar}{bar:30}{r_bar}{bar:-10b}', position=0):
        task_counter += 1
        game_counter += 1
        tasks.append(get_game_data(str(games[index]["appid"])))

        if task_counter < max_step and index < above - 1:
            continue

        response_games = await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(13)

        for game in response_games:
            check_failed_game = game.get('appid', '')

            if check_failed_game == '':
                games_format_data_dict.update(game)
            else:
                failed_games_list.append(game)

        if game_counter >= quantity_write or index == above - 1:
            if config['repeat']:
                # ready list games for repeat requests
                for_repeat = [game for game in failed_games_list
                              if game['reason'] != 'is not game' and game['reason'] != 'not released']

                failed_games_list = [fail for fail in failed_games_list if fail not in for_repeat]

                result = await repeat_get_games(for_repeat)
                games_format_data_dict.update(result['success'])
                failed_games_list.extend(result['failed'])

            genres_from_games = []

            for game in games_format_data_dict:
                genres_from_games = list(set(genres_from_games) | set(game['genres']))

            update_genres(genres_from_games)

            write_json_file(games_format_data_dict, os.path.join(path_dir_games, str(uuid.uuid4()) + '.json'))
            games_format_data_dict.clear()

            write_json_file(failed_games_list, os.path.join(path_dir_failed_games, str(uuid.uuid4()) + '.json'))
            failed_games_list.clear()

            game_counter = 0

        task_counter = 0
        tasks.clear()


async def repeat_get_games(games: list):
    logging.debug('Repeat getting failed games')
    again_failed = []
    success_games = {}

    for raw_game in tqdm(games, desc='repeat',
                         bar_format='{l_bar}{bar:30}{r_bar}{bar:-10b}', position=1, leave=False):
        format_game = await get_game_data(raw_game['appid'])
        await asyncio.sleep(1)

        try_game_id = format_game.get(raw_game['appid'], '')

        if try_game_id == '':
            again_failed.append(format_game)
        else:
            success_games.update(format_game)

    return {'success': success_games, 'failed': again_failed}


def write_json_file(games_list, path_file: str):
    with open(path_file, 'w', encoding='utf-8') as f:
        json.dump(games_list, f, ensure_ascii=False, indent=4)
        f.close()


def read_json_file(path_file: str):
    if not os.path.exists(path_file):
        logging.warning(f'File not exists: {path_file}')

    f = open(path_file, 'r', encoding='utf-8')
    json_data = json.load(f)
    f.close()

    return json_data


async def get_steam_html():
    logging.info(f'Getting all genres')
    try:
        async with aiohttp.ClientSession() as session:
            headers = {'Accept-Language': 'en-US'}
            async with session.get('https://store.steampowered.com/', headers=headers,
                                   allow_redirects=False) as response:
                return await response.text()
    except asyncio.TimeoutError as timeout_error:
        message_error = f'Timeout error getting genres'
        logging.error(message_error)
        return None


def scrape_genres(html: str):
    soup = BeautifulSoup(html, "html.parser")
    genres = []

    # Находим все элементы с классом "popup_genre_expand_content"
    genre_blocks = soup.find_all(class_="popup_genre_expand_content")

    # Проходим по каждому блоку с жанрами
    for block in genre_blocks:
        # Находим все ссылки в текущем блоке
        links = block.find_all("a")
        # Извлекаем текст из каждой ссылки и добавляем его в список
        for link in links:
            genre = link.get_text(strip=True)
            genres.append(genre)

    return genres


def update_genres(genres: list):
    path_genres_json_file = os.path.join(outputs_dir, 'genres.json')
    genres_from_file = read_json_file(path_genres_json_file)
    all_genres = list(set(genres_from_file) | set(genres))
    write_json_file(all_genres, path_genres_json_file)
    return all_genres


async def main():
    logging.info(f'Program started with params:\n'
                 f'\t\t\t\tabove: {config['above']}\n'
                 f'\t\t\t\tbelow: {config['below']}\n'
                 f'\t\t\t\tquantity_write: {config['quantity_write']}\n'
                 f'\t\t\t\tfile: {config['file']}\n'
                 f'\t\t\t\trepeat: {config['repeat']}\n')

    path_json_file = config['file'] if config['file'] is not None else ''

    html = await get_steam_html()

    if html is not None:
        genres = scrape_genres(html)
        all_genres = update_genres(genres)

    if path_json_file != '':
        logging.info(f'Getting list of games from file {path_json_file}')
        games = read_json_file(path_json_file)
    else:
        logging.info(f'Getting list of games from url')
        games = get_all_games()
        write_json_file(games, os.path.join(outputs_dir, 'games.json'))

        games = [game for game in games if game['name'] != '']
        logging.debug(f"Found games amount: {len(games)}")

    b = config['below'] if config['below'] is not None else 0
    a = config['above'] if config['above'] is not None else len(games)
    q = config['quantity_write'] if config['quantity_write'] is not None else 1000

    await write_games_info(games, b, a, q)


if __name__ == "__main__":
    message = f'Program has been run at {now}\n'
    print(message)
    logging.info(message)
    asyncio.run(main())
