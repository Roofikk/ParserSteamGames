import requests
from bs4 import BeautifulSoup

def get_all_games():
    games_url = "https://api.steampowered.com/ISteamApps/GetAppList/v2?format=json"
    response_json = requests.get(games_url).json()
    # soup = BeautifulSoup(response_json)
    return response_json["applist"]["apps"]

def get_game_info(game_id):
    url = f"https://store.steampowered.com/api/appdetails?appids={game_id}"
    response_json = requests.get(url).json()
    return response_json

if __name__ == "__main__":
    games = get_all_games()

    for game in games:
        response = get_game_info(game["appid"])

