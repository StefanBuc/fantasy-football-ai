from fastapi import APIRouter
from app.services.NFL_data import NFLData
from functools import lru_cache

router = APIRouter(prefix="/api/players", tags=["players"])

@lru_cache(maxsize=1)
def get_nfl_data() -> NFLData:
    nfl_data = NFLData()
    nfl_data.load_data()
    return nfl_data

@router.get("/")
def get_players():
    nfl_data = get_nfl_data()
    players = nfl_data.get_player_stats().to_dict(orient="records")
    return {"players": players}

@router.get("/{player_id}")
def get_player(player_id: int):
    nfl_data = get_nfl_data()
    players_df = nfl_data.get_player_stats()
    player = players_df[players_df["gsis_id"] == player_id].to_dict(orient="records")
    
    if not player:
        return {"error": "Player not found"}
    
    return {"player": player[0]}

@router.get("/{player_id}/stats")
def get_player_stats(player_id: int):
    nfl_data = get_nfl_data()
    players_df = nfl_data.get_player_stats()
    player_stats = players_df[players_df["gsis_id"] == player_id].to_dict(orient="records")
    
    if not player_stats:
        return {"error": "Player stats not found"}
    
    return {"player_stats": player_stats[0]}

@router.get("/{season}/{position}")
def get_players_by_season_and_position(season: int, position: str):
    nfl_data = get_nfl_data()
    players_df = nfl_data.get_player_stats()
    filtered_players = players_df[(players_df["season"] == season) & (players_df["position"] == position)].to_dict(orient="records")
    
    if not filtered_players:
        return {"error": "No players found for the given season and position"}
    
    return {"players": filtered_players}