from knowflix_engine.cover import pick_cover, score_figure


def test_score_figure_rewards_area_and_caption():
    small_no_caption = score_figure({"area_ratio": 0.05, "has_caption": False})
    large_with_caption = score_figure({"area_ratio": 0.6, "has_caption": True})
    assert large_with_caption > small_no_caption


def test_score_figure_is_deterministic():
    fig = {"area_ratio": 0.4, "has_caption": True}
    assert score_figure(fig) == score_figure(dict(fig))


def test_pick_cover_selects_highest_score():
    figures = [
        {"id": "fig_0_0", "area_ratio": 0.05, "has_caption": False},
        {"id": "fig_1_0", "area_ratio": 0.5, "has_caption": True},
        {"id": "fig_2_0", "area_ratio": 0.5, "has_caption": False},
    ]
    assert pick_cover(figures) == "fig_1_0"


def test_pick_cover_empty_list_returns_none():
    assert pick_cover([]) is None


def test_pick_cover_zero_score_figures_return_none():
    figures = [{"id": "fig_0_0", "area_ratio": 0.0, "has_caption": False}]
    assert pick_cover(figures) is None
