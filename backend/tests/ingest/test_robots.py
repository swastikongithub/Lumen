import pytest

from app.ingest.robots import ALLOW_ALL, DISALLOW_ALL, parse_robots, product_token

# Shaped like lpu.in's file: blank lines inside groups, AI agents allowed everywhere.
LPU_LIKE = """
User-agent: *

Disallow: /downloads
Disallow: /sustainable

Sitemap: https://www.lpu.in/sitemap.xml

User-agent: ClaudeBot
User-agent: GPTBot
Allow: /
"""


def test_blank_lines_do_not_end_a_group() -> None:
    robots = parse_robots(LPU_LIKE)

    assert not robots.allows("LumenBot", "https://www.lpu.in/downloads/policy.pdf")
    assert not robots.allows("LumenBot", "/sustainable/sdg10/x.php")
    assert robots.allows("LumenBot", "/academics/calendar.php")


def test_named_group_beats_the_star_group() -> None:
    robots = parse_robots(LPU_LIKE)

    assert robots.allows("ClaudeBot", "/downloads/policy.pdf")
    assert robots.allows("gptbot", "/sustainable/x.php")  # token match is case-insensitive


def test_paths_are_case_sensitive() -> None:
    robots = parse_robots(LPU_LIKE)

    assert robots.allows("LumenBot", "/SUSTAINABLE/sdg10/x.php")


def test_longest_match_wins_and_allow_wins_ties() -> None:
    robots = parse_robots(
        "User-agent: *\nDisallow: /docs\nAllow: /docs/public\nAllow: /x\nDisallow: /x\n"
    )

    assert not robots.allows("Bot", "/docs/private.pdf")
    assert robots.allows("Bot", "/docs/public/a.pdf")
    assert robots.allows("Bot", "/x/page")


def test_wildcards_and_end_anchor() -> None:
    robots = parse_robots("User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp*/cache\n")

    assert not robots.allows("Bot", "/files/a.pdf")
    assert robots.allows("Bot", "/files/a.pdf?download=1")
    assert not robots.allows("Bot", "/tmp-2/cache/x")
    assert robots.allows("Bot", "/files/a.html")


def test_percent_encoding_is_compared_decoded() -> None:
    robots = parse_robots("User-agent: *\nDisallow: /Static Information/\n")

    assert not robots.allows("Bot", "https://ums.lpu.in/Static%20Information/a.pdf")


def test_empty_disallow_and_missing_groups_allow_everything() -> None:
    assert parse_robots("User-agent: *\nDisallow:\n").allows("Bot", "/anything")
    assert parse_robots("User-agent: OtherBot\nDisallow: /\n").allows("Bot", "/anything")
    assert parse_robots("").allows("Bot", "/anything")


def test_rules_before_any_user_agent_are_ignored() -> None:
    robots = parse_robots("Disallow: /\nUser-agent: *\nAllow: /\n")

    assert robots.allows("Bot", "/page")


def test_robots_txt_itself_is_always_allowed() -> None:
    assert DISALLOW_ALL.allows("Bot", "/robots.txt")
    assert not DISALLOW_ALL.allows("Bot", "/page")
    assert ALLOW_ALL.allows("Bot", "/page")


@pytest.mark.parametrize(
    ("user_agent", "token"),
    [("LumenBot/0.1", "LumenBot"), ("LumenBot", "LumenBot"), ("LumenBot (+info)", "LumenBot")],
)
def test_product_token(user_agent: str, token: str) -> None:
    assert product_token(user_agent) == token
