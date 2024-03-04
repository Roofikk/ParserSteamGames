import asyncio
import json
import os
import uuid
from datetime import datetime
import aiohttp
import re
from bs4 import BeautifulSoup
from tqdm import tqdm
import logging


async def get_request(uri: str):
    session_timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=10)
    try:
        async with aiohttp.ClientSession(timeout=session_timeout, trust_env=True) as session:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                                     'Chrome/121.0.0.0 Safari/537.36'}
            async with session.get(uri, headers=headers, allow_redirects=True, timeout=10) as response:
                if response.status == 200 or response.status == 301:
                    return await response.text()
    except asyncio.TimeoutError as e:
        logging.warning(f'Timeout error: {uri}')
        return None
    except aiohttp.ClientConnectorError:
        logging.warning(f'Connection failed: {uri}')
        return None

async def get_game_data(uri: str):
    try_count = 0

    while try_count < 5:
        html_text = await get_request(uri)
        if html_text is not None:
            logging.info(f'The game page has been opened: {uri}')
            return scrape_game_info(html_text, uri)
        try_count += 1
        await asyncio.sleep(1)

    logging.warning(f'The game page does not opened: {uri}')
    return None


async def get_game_links_from_page(uri: str):
    try_count = 0
    html_text = None

    while try_count < 5:
        html_text = await get_request(uri)
        if html_text is not None:
            break
        try_count += 1
        await asyncio.sleep(1)

    if html_text is None:
        logging.warning(f'The page does not open: {uri}')
        return None

    logging.info(f'The page has been opened: {uri}')
    return scrape_game_links(html_text)


def scrape_game_links(html_text: str):
    list_games_uri = []
    soup = BeautifulSoup(html_text, 'html.parser')
    main_class = soup.find('main', class_='main')
    game_divs = main_class.find_all('div', class_='short_title')

    for div in game_divs:
        link = div.find('a')
        list_games_uri.append(link['href'])

    return list_games_uri


def scrape_game_info(html_text: str, uri: str):
    if html_text is None:
        logging.warning(f'Game does not opened: {uri}')
        return

    game_info = {'uri': uri}
    soup = BeautifulSoup(html_text, 'html.parser')

    # getting game name
    div_game_name = soup.find('div', class_='hname')
    game_name = div_game_name.find('h1').text.strip()
    game_info['name'] = game_name

    # getting game description
    game_desc = soup.find('div', class_='game_desc')
    game_info['description'] = str(game_desc)

    # getting screenshots
    screenshots = []
    screen_tags = soup.find_all('a', class_='fresco')
    for a in screen_tags:
        screenshots.append(a['href'])

    # getting video
    soup_video_webm = soup.find('source', attrs={'type': 'video/webm'})
    if soup_video_webm is not None:
        video_webm = soup_video_webm.attrs.get('src', 'Not found')
        game_info['video_webm'] = str(video_webm)
    else:
        game_info['video_webm'] = 'Not found'

    soup_video_mp4 = soup.find('source', attrs={'type': 'video/mp4'})
    if soup_video_mp4 is not None:
        video_mp4 = soup_video_webm.attrs.get('src', 'Not found')
        game_info['video_mp4'] = str(video_mp4)
    else:
        game_info['video_mp4'] = 'Not found'

    # getting release date
    soup_release_date = soup.find('span', class_='dateym')
    if soup_release_date is not None:
        game_info['release_date'] = soup_release_date.text.strip()
    else:
        game_info['release_date'] = 'Not found'

    # getting release year
    soup_release_year = soup.find('a', class_='link-year')
    if soup_release_year is not None:
        release_year_text = soup_release_year.text
        release_year_match = re.search(r'^\D*[0-9,.]+', release_year_text)
        game_info['release_year'] = int(release_year_match[0])
    else:
        game_info['release_year'] = -1

    tech_details_clearfix = soup.find('div', class_='tech_details clearfix')
    tech_details_blocks = tech_details_clearfix.find_all('div', class_='tech_details-block')
    lis = tech_details_blocks[0].find_all('li')

    for li in lis:
        span = li.find('span')
        match span.text:
            case 'Жанр:':
                genres = [genre.text for genre in li.find_all('a')]
                game_info['genres'] = genres
            case 'Разработчик:':
                game_info['developers'] = span.next_sibling.text.strip()
            case 'Интерфейс:':
                sib = span.next_sibling
                text = ''

                while True:
                    text = sib.text.strip()
                    if text == '' or text.find('class') > 0:
                        sib = sib.next_sibling
                        continue
                    else:
                        break

                game_info['ui_language'] = text
            case 'Озвучка:':
                game_info['sound_language'] = span.next_sibling.text.strip()

    # getting categories (tags)
    soup_tags = soup.find('div', class_='apptag')
    if soup_tags is not None:
        a_tags = soup_tags.find_all('a')
        game_info['categories'] = [tag.text for tag in a_tags]
    else:
        game_info['categories'] = []

    # getting game version
    soup_div_info = soup.find('div', class_='info_type')
    if soup_div_info is not None:
        version_text = soup_div_info.find('b').text
        # version_match = re.search(r'v\s*[0-9,.]*', version_text)
        game_info['version'] = version_text
    else:
        game_info['version'] = 'Not found'

    # getting game size
    soup_game_size = soup.find('div', class_='persize_bottom')
    if soup_game_size is not None:
        size_text = soup_game_size.find('span')
        # убрал регулярку на вытягивание только числа, потому что некоторые игры считаются в Мб.
        # size_match = re.search(r'^[0-9,.]+', size_text.text)
        game_info['torrent_size'] = float(size_text.text.strip())
    else:
        game_info['torrent_size'] = float(-1)

    # getting requirements
    if len(tech_details_blocks) > 1:
        lis = tech_details_blocks[1].find_all('li')
        fields = []
        for li in lis:
            span = li.find('span')
            req_property = span.text.strip()
            req_property_match = re.search(r'^(.+?):$', req_property)
            value = span.next_sibling.text.strip()
            fields.append({'property': req_property_match.group(1), 'value': value})

        game_info['requirements'] = fields
    else:
        game_info['requirements'] = []

    logging.info(f'Game has been scraped: {game_info['name']}')
    return game_info


def write_json_file(games_list, path_file: str):
    with open(path_file, 'w', encoding='utf-8') as f:
        json.dump(games_list, f, ensure_ascii=False, indent=4)
        f.close()


async def main():
    # getting max count page
    uri = 'https://thebyrut.org/'
    html_text = await get_request(uri)
    soup = BeautifulSoup(html_text, 'html.parser')
    soup_div_pages = soup.find('div', class_='pages')
    soup_a_pages = soup_div_pages.find_all('a')
    last_page = int(soup_a_pages[-1].text)

    games_links = []

    for page_count in tqdm(range(1, last_page + 1), desc='get game links',
                           bar_format='{l_bar}{bar:30}{r_bar}{bar:-10b}', position=0):
        uri = f'https://thebyrut.org/page/{page_count}/'
        games_links.extend(await get_game_links_from_page(uri))

    games_links = list(dict.fromkeys(games_links))
    count_game_for_write = 1200
    game_index = 0
    games_for_json_write = []
    get_games_tasks = []

    for link in tqdm(games_links, desc='format games',
                     bar_format='{l_bar}{bar:30}{r_bar}{bar:-10b}', position=0):
        get_games_tasks.append(get_game_data(link))
        game_index += 1

        if game_index >= count_game_for_write:
            games = await asyncio.gather(*get_games_tasks, return_exceptions=True)

            games = [game for game in games if game is not None]
            games_for_json_write.extend(games)

            write_json_file(games_for_json_write, os.path.join(dir_games_path, str(uuid.uuid4()) + '.json'))
            games_for_json_write.clear()
            get_games_tasks.clear()
            game_index = 0

    if len(games_for_json_write) > 0:
        write_json_file(games_for_json_write, os.path.join(dir_games_path, str(uuid.uuid4()) + '.json'))
        games_for_json_write.clear()


if __name__ == '__main__':
    now = datetime.now().strftime('%d-%m-%Y %H-%M-%S')
    outputs_dir = os.path.join(os.getcwd(), 'outputs', 'byrutor')
    dir_games_path = os.path.join(outputs_dir, now)
    os.makedirs(dir_games_path)

    logging.basicConfig(filename=os.path.join(dir_games_path, f'logs-{now}.log'), encoding='utf-8',
                        format='%(asctime)s.%(msecs)03d %(message)s', datefmt='%d-%m-%Y %H:%M:%S', level=logging.DEBUG)
    asyncio.run(main())
