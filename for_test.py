import argparse
import json
import logging
import asyncio
import os
import aiohttp
from bs4 import BeautifulSoup

parser = argparse.ArgumentParser(description='Steam Parser', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('-a', '--above', type=int, help='The upper limit of the parsing list, default: max')
parser.add_argument('-b', '--below', type=int, help='The lower limit of the parsing list, default: 0')
parser.add_argument('-q', '--quantity-write', type=int,
                    help='Which quantity parsing entry for writing json file, default: 1000')
parser.add_argument('-f', '--file', type=str,
                    help='Any full path to json file which was created on last parses, default: takes from url request')

logging.basicConfig(filename='logs.log', encoding='utf-8',
                    format='%(asctime)s %(message)s', datefmt='%d-%m-%Y %H:%M:%S', level=logging.INFO)

outputs_dir = os.path.join(os.getcwd(), 'outputs')


async def get_all_genres():
    logging.info(f'Getting all genres')
    try:
        async with aiohttp.ClientSession() as session:
            headers = {'Accept-Language': 'en-US'}
            async with session.get('https://store.steampowered.com/', headers=headers,
                                   allow_redirects=False) as response:
                if response.status == 200:
                    return scrape_genres(await response.text())
    except asyncio.TimeoutError as timeout_error:
        message_error = f'Timeout error getting genres'
        logging.error(message_error)
        return {}


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

    path_genres_json_file = os.path.join(outputs_dir, 'genres.json')
    genres_from_file = read_json_file(path_genres_json_file)
    all_genres = list(set(genres_from_file) | set(genres))
    write_json_file(all_genres, path_genres_json_file)
    return genres


def read_json_file(path_file: str):
    f = open(path_file, 'r', encoding='utf-8')
    json_data = json.load(f)
    f.close()

    return json_data


def write_json_file(games_list, path_file: str):
    with open(path_file, 'w', encoding='utf-8') as f:
        json.dump(games_list, f, ensure_ascii=False, indent=4)
        f.close()


async def get_stored_steam_game_html(game_id):
    logging.info(f'Getting game from steam store')
    try:
        async with aiohttp.ClientSession() as session:
            headers = {'Accept-Language': 'en-US'}
            async with session.get(f'https://store.steampowered.com/app/{game_id}', headers=headers,
                                   allow_redirects=False) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    print(f'Failed to access. Status: {response.status}, game id: {game_id}')
                    return None
    except asyncio.TimeoutError as timeout_error:
        message_error = f'Timeout error'
        logging.error(message_error)
        return None


def scrape_steam_game_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    game_name_by_id = soup.find('div', id='appHubAppName')

    if game_name_by_id is not None:
        return game_name_by_id.text

    game_name_by_class = soup.find('div', class_='apphub_AppName')

    if game_name_by_class is not None:
        return game_name_by_class.text
    else:
        return None


async def main():
    games = read_json_file(os.path.join('outputs', 'games.json'))
    count_try = 0
    tasks = []
    for game in games:
        tasks.append(get_stored_steam_game_html(game['appid']))

        if len(tasks) >= 20:
            htmls = await asyncio.gather(*tasks, return_exceptions=True)

            for html in htmls:
                if html is not None:
                    print(f'Success getting game :)')
                else:
                    print('Something wrong :(')

            tasks.clear()
            await asyncio.sleep(1)

        count_try += 1

    print(count_try)


def get_description_text(html: str):
    soup = BeautifulSoup(html, 'html.parser')

    if soup is not None:
        return soup.text
    else:
        return None


if __name__ == '__main__':
    asyncio.run(main())
