from espn_api.football import League

def get_league(league_id, year = 2026, espn_s2 = None, swid = None):
    return League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)

def find_team(league, team_id):
    return next(
        team for team in league.teams
        if team.team_id == team_id
    )

def get_team_roster(league, team_id):
    return find_team(league, team_id).roster

def get_team_schedule(league, team_id):
    return find_team(league, team_id).schedule

def get_team_matchups(league, week):
    return league.scoreboard(matchupPeriod=week)

def get_league_standings(league):
    return league.standings()

def get_league_transactions(league):
    return league.transactions()

def get_league_free_agents(league):
    return league.free_agents()