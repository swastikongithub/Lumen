"""robots.txt parsing and matching per RFC 9309.

Python's `urllib.robotparser` ends a group at a blank line, which RFC 9309 does not,
so it misreads files like lpu.in's that put blank lines inside a group. This module
follows the RFC instead:

- A group is one or more `user-agent` lines followed by rules; it ends at the next
  `user-agent` line that comes after a rule. Blank lines and unknown keys
  (sitemap, crawl-delay, content-signal) do not end a group.
- A crawler obeys the group naming its product token (case-insensitive), otherwise
  the `*` group, otherwise nothing is disallowed.
- The longest matching rule wins; on a tie `allow` wins. `*` matches any characters
  and a trailing `$` anchors the end of the path. Paths are case-sensitive.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit


@dataclass(frozen=True)
class Rule:
    allow: bool
    pattern: str

    def matches(self, path: str) -> bool:
        return _compile(self.pattern).match(path) is not None


@dataclass
class Robots:
    # Lower-case user-agent token -> its rules, merged across groups.
    groups: dict[str, list[Rule]] = field(default_factory=dict)

    def allows(self, product_token: str, url_or_path: str) -> bool:
        path = request_path(url_or_path)
        if path == "/robots.txt":
            return True
        rules = self.groups.get(product_token.lower())
        if rules is None:
            rules = self.groups.get("*", [])
        best: Rule | None = None
        for rule in rules:
            if not rule.matches(path):
                continue
            longer = best is None or len(rule.pattern) > len(best.pattern)
            tie_allow = best is not None and len(rule.pattern) == len(best.pattern) and rule.allow
            if longer or tie_allow:
                best = rule
        return best is None or best.allow


ALLOW_ALL = Robots()
DISALLOW_ALL = Robots({"*": [Rule(allow=False, pattern="/")]})


def parse_robots(text: str) -> Robots:
    robots = Robots()
    agents: list[str] = []  # user-agents of the group being read
    seen_rule = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if seen_rule:  # a user-agent line after rules starts a new group
                agents, seen_rule = [], False
            agents.append(value.lower())
            robots.groups.setdefault(value.lower(), [])
        elif key in ("allow", "disallow"):
            if not agents:  # rules before any user-agent line belong to no group
                continue
            seen_rule = True
            if not value:  # "Disallow:" with no path disallows nothing
                continue
            for agent in agents:
                robots.groups[agent].append(Rule(allow=key == "allow", pattern=unquote(value)))
    return robots


def request_path(url_or_path: str) -> str:
    """The decoded path and query that rules are matched against."""
    parts = urlsplit(url_or_path)
    path = unquote(parts.path) or "/"
    return f"{path}?{unquote(parts.query)}" if parts.query else path


def product_token(user_agent: str) -> str:
    """'LumenBot/0.1 (+info)' -> 'LumenBot'."""
    return user_agent.split("/", 1)[0].split()[0]


_PATTERNS: dict[str, re.Pattern[str]] = {}


def _compile(pattern: str) -> re.Pattern[str]:
    compiled = _PATTERNS.get(pattern)
    if compiled is None:
        anchored = pattern.endswith("$")
        body = pattern[:-1] if anchored else pattern
        regex = ".*".join(re.escape(part) for part in body.split("*"))
        compiled = re.compile(regex + ("$" if anchored else ""), re.DOTALL)
        _PATTERNS[pattern] = compiled
    return compiled
