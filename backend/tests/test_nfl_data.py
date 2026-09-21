from urllib.error import HTTPError

import numpy as np
import pandas as pd

from app.services import NFL_data as nfl_data_module
from app.services.NFL_data import (
    NFLData,
    WEEKLY_PLAYER_STATS_URL,
)


def test_weekly_data_uses_new_nflverse_release_after_404(
    monkeypatch,
):
    def fail_legacy_download(seasons):
        raise HTTPError(
            url="legacy-url",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    loaded_urls = []

    def load_current_release(url):
        loaded_urls.append(url)
        return pd.DataFrame(
            {
                "season": [2025],
                "team": ["BUF"],
                "fantasy_points": np.array(
                    [20.0],
                    dtype=np.float64,
                ),
            }
        )

    monkeypatch.setattr(
        nfl_data_module.nfl,
        "import_weekly_data",
        fail_legacy_download,
    )
    monkeypatch.setattr(
        nfl_data_module.pd,
        "read_parquet",
        load_current_release,
    )

    result = NFLData([2025])._load_weekly_player_data()

    assert loaded_urls == [
        WEEKLY_PLAYER_STATS_URL.format(season=2025)
    ]
    assert "recent_team" in result.columns
    assert "team" not in result.columns
    assert result.loc[0, "recent_team"] == "BUF"
    assert result["fantasy_points"].dtype == np.float32
